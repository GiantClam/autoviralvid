import os
import json
import asyncio
import logging
import uuid
from typing import TypedDict, List, Dict, Any, Annotated, Optional, Union
import operator
from datetime import datetime

from langgraph.graph import StateGraph, END, add_messages
from langgraph.types import Command
from typing_extensions import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig

# [NEW] CopilotKit State and Utils
from copilotkit import CopilotKitState
from src.util import should_route_to_tool_node

# Import existing tools and logic
from src.agent_skills import (
    plan_storyboard_impl,
    generate_video_clip_impl,
    merge_storyboards_to_video_tasks_impl,
)
from src.providers import get_image_provider, get_video_provider
from src.r2 import upload_url_to_r2
from src.job_manager import job_manager

logger = logging.getLogger("langgraph_workflow")

# --- State Definition ---


class AgentState(TypedDict):
    """
    Agent state using TypedDict for standard LangGraph compatibility.
    Inherits fields logically from what CopilotKit expects (messages).
    """

    # LangGraph standard messages with reducer
    messages: Annotated[List[BaseMessage], add_messages]

    # Input / Context
    goal: Optional[str]
    styles: Optional[List[str]]
    total_duration: Optional[float]
    clip_duration: Optional[float]
    num_clips: Optional[int]
    image_control: Optional[bool]
    run_id: Optional[str]
    thread_id: Optional[str]

    # Internal Data
    storyboard: Optional[Dict[str, Any]]
    video_tasks: Optional[List[Dict[str, Any]]]
    clip_results: Optional[List[Dict[str, Any]]]
    collected_info: Optional[Dict[str, Any]]

    # Output
    final_video_url: Optional[str]
    final_audio_url: Optional[str]

    # Control Flags Status
    use_avatar: Optional[bool]
    platform: Optional[str]
    status: str
    review_status: Optional[str]
    error: Optional[str]
    loop_count: Optional[int]

    # Pipeline-based orchestration
    selected_pipeline: Optional[str]  # Pipeline name (e.g. "sora2")
    selected_skills: Optional[List[str]]  # Ordered list of I2V skill names for fallback
    selected_image_skill: Optional[str]  # Pipeline-companion T2I skill name
    selected_i2v_skill: Optional[str]  # Pipeline-companion I2V skill name


def sget(state, key, default=None):
    """Safe state access that handles both dict and object."""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def sfloat(value, default: float) -> float:
    """Best-effort float coercion with fallback."""
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


# --- Nodes Implementation ---

from src.creative_agent import (
    extract_project_info,
    submit_production_plan,
    STYLE_OPTIONS,
    DURATION_OPTIONS,
    ORIENTATION_OPTIONS,
)


# Initialize LLM with OpenRouter
def get_llm(model_key="PROMPT_LLM_MODEL"):
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
    model_name = os.getenv(model_key, "anthropic/claude-3.5-sonnet")
    proxy = os.getenv("OPENROUTER_PROXY")

    http_client = None
    if proxy:
        import httpx

        http_client = httpx.AsyncClient(proxy=proxy)

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        base_url=base_url,
        temperature=0,
        http_async_client=http_client,
        default_headers={
            "HTTP-Referer": os.getenv("EMBEDDING_REFERER", "http://localhost:3000"),
            "X-Title": "AiCapcut Agent",
        },
    )


llm = get_llm("PROMPT_LLM_MODEL")
storyboard_llm = get_llm("STORYBOARD_LLM_MODEL")


async def supervisor_node(state: AgentState):
    """
    Supervisor node - handles routing only, minimal state updates.
    Route decisions are made by supervisor_route() function via conditional edges.
    Only updates state for explicit user commands like "accept".
    """
    try:
        print("[DEBUG] supervisor_node invoked")
        run_id = sget(state, "run_id")
        if not run_id or run_id == "unknown":
            run_id = str(uuid.uuid4())
            print(f"[WARN] supervisor: Generated new run_id={run_id}")

        status = sget(state, "status", "gathering")
        logger.info(f"\n>>>> [AGENT: SUPERVISOR] run_id={run_id}, status={status} <<<<")
        print(f"[DEBUG] supervisor_node run_id={run_id}, status={status}")

        messages = sget(state, "messages", [])
        msg = messages[-1].content if messages else ""

        # Normalize message for robust matching (handle encoding variations)
        normalized_msg = msg.strip() if isinstance(msg, str) else ""
        logger.debug(
            f"[SUPERVISOR] Last message raw: {repr(msg)}, normalized: {repr(normalized_msg)}"
        )

        # Handle explicit user commands (these ARE state updates)
        # Robust approval trigger matching with multiple fallbacks
        approval_triggers = {"accept"}
        is_approval = normalized_msg in approval_triggers

        if is_approval:
            if status == "awaiting_approval":
                print(
                    "[DEBUG] supervisor: User approved storyboard, transitioning to generating"
                )
                return {
                    "status": "generating",
                    "run_id": run_id,
                    "thoughts": "User approved storyboard. Starting to generate visual assets.",
                    "messages": [
                        AIMessage(
                            content="Great! The core script is confirmed. I’m starting to render the video assets now. Please wait a moment."
                        )
                    ],
                }
            if status == "awaiting_stitch_approval":
                print(
                    "[DEBUG] supervisor: User confirmed stitching, transitioning to ready_to_stitch"
                )
                return {
                    "status": "ready_to_stitch",
                    "run_id": run_id,
                    "thoughts": "User approved assets. Starting final stitching.",
                    "messages": [
                        AIMessage(
                            content="Got it! All assets are ready. Starting final stitching now. You’ll have the full video shortly."
                        )
                    ],
                }

        if "retry" in normalized_msg.lower():
            if status == "awaiting_approval":
                import re

                scene_match = re.search(
                    r"scene\\s*(\\d+)", normalized_msg, re.IGNORECASE
                )
                if scene_match:
                    idx = int(scene_match.group(1)) - 1
                    storyboard = sget(state, "storyboard", {})
                    if (
                        storyboard
                        and "scenes" in storyboard
                        and 0 <= idx < len(storyboard["scenes"])
                    ):
                        scene = storyboard["scenes"][idx]
                        if "keyframes" in scene:
                            scene["keyframes"].pop("in", None)
                        scene["visual_status"] = "retrying"
                        scene.pop("visual_error", None)
                        msg_text = f"Got it. I’m regenerating the image for scene {idx + 1}. Please wait."
                        return {
                            "status": "visualizing",
                            "storyboard": storyboard,
                            "run_id": run_id,
                            "thoughts": f"Regenerating image for scene {idx + 1}.",
                            "messages": [AIMessage(content=msg_text)],
                        }

                if "retry" in normalized_msg.lower():
                    # Clear visual_status for ALL failed scenes to trigger re-gen in image_gen_node
                    storyboard = sget(state, "storyboard", {})
                    if storyboard and "scenes" in storyboard:
                        for scene in storyboard["scenes"]:
                            if scene.get("visual_status") == "failed":
                                scene.pop("visual_status", None)
                                scene.pop("visual_error", None)
                                if "keyframes" in scene:
                                    scene["keyframes"].pop("in", None)

                    return {
                        "status": "visualizing",
                        "storyboard": storyboard,
                        "run_id": run_id,
                        "thoughts": "Retrying failed storyboard renders.",
                        "messages": [
                            AIMessage(
                                content="No problem. I’ll retry all failed storyboard renders now."
                            )
                        ],
                    }

            if status == "awaiting_stitch_approval":
                # For video clips, we just need to go back to generating stage.
                # executor_node will handle the smart skipping.
                return {
                    "status": "generating",
                    "thoughts": "Regenerating failed video clips.",
                    "messages": [
                        AIMessage(
                            content="No problem. I’ll retry the failed clips now. Please check again shortly."
                        )
                    ],
                }

        if status == "failed":
            error_msg = sget(
                state, "error", "An unknown error occurred during processing."
            )
            print(f"[DEBUG] supervisor: Workflow failed with error: {error_msg}")
            return {
                "thoughts": f"The workflow has failed: {error_msg}",
                "messages": [
                    AIMessage(
                        content=f"I'm sorry, but something went wrong: {error_msg}. You can try to fix the issue or retry the last step."
                    )
                ],
            }

        # For all other cases, return empty dict - no state updates
        # Routing is handled by supervisor_route() via conditional edges
        return {}
    except Exception as e:
        logger.exception(f"  [SUPERVISOR] Node failed: {e}")
        return {"error": str(e), "status": "failed"}


async def gatherer_node(
    state: AgentState, config: RunnableConfig
) -> Command[Literal["supervisor"]]:
    """
    Specialized Agent for Information Gathering using Command pattern.
    """
    try:
        run_id = sget(state, "run_id", "unknown")
        print(f"[DEBUG] gatherer_node invoked, run_id={run_id}")
        logger.info(f"\n>>>> [AGENT: GATHERER] run_id={run_id} <<<<")

        collected_info = sget(state, "collected_info", {}) or {}
        messages = sget(state, "messages", [])

        # Pre-process: Extract image URL and template_id from user messages if present
        import re

        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                content = msg.content
                # Check for image upload pattern: [Product image uploaded] URL
                if (
                    "[Product image uploaded]" in content
                    or "[产品图片已上传]" in content
                ):
                    url_match = re.search(r"https?://[^\s]+", content)
                    if url_match and not collected_info.get("product_image"):
                        collected_info["product_image"] = url_match.group(0)
                        logger.info(
                            f"  [GATHERER] Extracted product_image from message: {collected_info['product_image']}"
                        )
                # Check for template selection: [template:xxx]
                tpl_match = re.search(r"\[template:([a-z0-9-]+)\]", content)
                if tpl_match and not collected_info.get("template_id"):
                    collected_info["template_id"] = tpl_match.group(1)
                    logger.info(
                        f"  [GATHERER] Extracted template_id from message: {collected_info['template_id']}"
                    )
                    # Auto-set video_type and pipeline_hint from template config
                    try:
                        from src.creative_agent import (
                            TEMPLATE_CONFIG,
                            get_pipeline_hint_for_template,
                        )

                        tpl_cfg = TEMPLATE_CONFIG.get(collected_info["template_id"], {})
                        if tpl_cfg.get("video_type") and not collected_info.get(
                            "video_type"
                        ):
                            collected_info["video_type"] = tpl_cfg["video_type"]
                        pipeline_hint = get_pipeline_hint_for_template(
                            collected_info["template_id"]
                        )
                        if pipeline_hint:
                            collected_info["pipeline_hint"] = pipeline_hint
                            logger.info(
                                f"  [GATHERER] Pipeline hint from template: {pipeline_hint}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"  [GATHERER] Failed to load template config: {e}"
                        )

        # 1. Define tools
        tools = [extract_project_info, submit_production_plan]

        # 2. Bind frontend actions and local tools
        fe_tools = state.get("copilotkit", {}).get("actions", [])
        llm_with_tools = llm.bind_tools([*fe_tools, *tools])

        system_prompt = f"""You are a creative video production assistant helping users bring their ideas to life.
Your personality: warm, enthusiastic, and professional — like a talented director meeting a new client.

Your goal is to understand what kind of video the user wants to create, step by step.
Don't ask for everything at once — have a natural conversation.

What we know so far: {json.dumps(collected_info, ensure_ascii=False)}

INFORMATION TO GATHER (in natural order):
1. What the video is about (theme) → extract from user's description naturally
2. A product/reference image → ask them to upload one
3. Visual style → must be chosen from: {json.dumps(STYLE_OPTIONS, ensure_ascii=False)}
   IMPORTANT: Never guess the style from text. Wait for explicit selection.
4. Duration → from options: {json.dumps(DURATION_OPTIONS, ensure_ascii=False)} seconds
5. Orientation → from options: {json.dumps(ORIENTATION_OPTIONS, ensure_ascii=False)}

CONVERSATION GUIDELINES:
- Use the user's language (Chinese if they write Chinese, English if English)
- Be encouraging: "That sounds amazing!" "Great choice!"
- Give brief creative suggestions when relevant
- Keep responses concise (2-3 sentences max)
- Call `extract_project_info` when the user provides any detail
- Call `submit_production_plan` only when theme AND product_image are both present
- Never mention technical terms like "field", "parameter", "node", "workflow"
"""
        llm_messages = [SystemMessage(content=system_prompt)] + messages
        response = await llm_with_tools.ainvoke(llm_messages, config)

        new_info = collected_info.copy()
        status = "gathering"

        if response.tool_calls:
            for tc in response.tool_calls:
                if tc["name"] == "extract_project_info":
                    new_info.update(tc["args"])
                elif tc["name"] == "submit_production_plan":
                    status = "planning"
        # Normalize duration to int when possible
        if "duration" in new_info and new_info.get("duration") is not None:
            try:
                new_info["duration"] = int(float(new_info.get("duration")))
            except Exception:
                pass

        # Auto-transition: If all required fields are collected, transition to planning
        has_image = bool(new_info.get("product_image"))
        has_theme = bool(new_info.get("theme"))
        has_style = bool(new_info.get("style"))
        has_duration = bool(new_info.get("duration"))
        has_orientation = bool(new_info.get("orientation"))

        print(
            f"[DEBUG] gatherer check: image={has_image}, theme={has_theme}, style={has_style}"
        )
        print(f"[DEBUG] collected_info: {new_info}")
        logger.info(
            "  [GATHERER] Checking transition: "
            f"has_image={has_image}, has_theme={has_theme}, has_style={has_style}, "
            f"has_duration={has_duration}, has_orientation={has_orientation}"
        )
        logger.info(
            f"  [GATHERER] collected_info: {json.dumps(new_info, ensure_ascii=False, default=str)}"
        )

        if (
            has_image
            and has_theme
            and has_style
            and has_duration
            and has_orientation
            and status == "gathering"
        ):
            print("[DEBUG] All required info collected, transitioning to planning!")
            logger.info(
                "  [GATHERER] All required info collected, transitioning to planning"
            )
            status = "planning"
            # Add a proactive message
            total_duration = sfloat(
                new_info.get("duration"), sget(state, "total_duration", 120.0) or 120.0
            )
            clip_duration = 10.0
            clip_count = int(total_duration / clip_duration) if total_duration else 0
            return {
                "status": "planning",
                "collected_info": new_info,
                "total_duration": total_duration,
                "clip_duration": clip_duration,
                "thoughts": "All required info collected. Preparing storyboard and segment plan.",
                "messages": [
                    AIMessage(
                        content=f"Great! Total duration: {int(total_duration)}s, clips: {clip_count} x 10s. I'll draft the storyboard now."
                    )
                ],
            }

        # Determine Tool Calls for UI and generate appropriate follow-up message
        ui_tool_calls = []
        follow_up_message = ""

        if status == "gathering":
            if not new_info.get("product_image"):
                ui_tool_calls.append(
                    {
                        "name": "request_upload",
                        "args": {
                            "description": "Please upload a product reference image."
                        },
                        "id": "call_upload_" + str(uuid.uuid4()),
                    }
                )
                if not response.content:
                    follow_up_message = "Please upload a product reference image."
            elif not new_info.get("theme"):
                if not response.content:
                    follow_up_message = (
                        "What is the main theme or marketing focus of this video?"
                    )
            elif not new_info.get("style"):
                ui_tool_calls.append(
                    {
                        "name": "request_selection",
                        "args": {
                            "question": "Please select a visual style.",
                            "options": STYLE_OPTIONS,
                            "multi_select": True,
                        },
                        "id": "call_style_" + str(uuid.uuid4()),
                    }
                )
                if not response.content:
                    follow_up_message = "Please select a visual style."
            elif not new_info.get("duration"):
                ui_tool_calls.append(
                    {
                        "name": "request_selection",
                        "args": {
                            "question": "Please select the total duration (seconds).",
                            "options": DURATION_OPTIONS,
                            "multi_select": False,
                        },
                        "id": "call_duration_" + str(uuid.uuid4()),
                    }
                )
                if not response.content:
                    follow_up_message = "Please select the total duration (seconds)."
            elif not new_info.get("orientation"):
                ui_tool_calls.append(
                    {
                        "name": "request_selection",
                        "args": {
                            "question": "Please select the video orientation (horizontal or vertical).",
                            "options": ORIENTATION_OPTIONS,
                            "multi_select": False,
                        },
                        "id": "call_orientation_" + str(uuid.uuid4()),
                    }
                )
                if not response.content:
                    follow_up_message = (
                        "Please select the video orientation (horizontal or vertical)."
                    )
            else:
                if not response.content:
                    follow_up_message = (
                        "Great! I have all required info and will draft the storyboard."
                    )
        elif status == "planning":
            # Transition to planning - always provide a meaningful message
            if not response.content:
                follow_up_message = "Great! All information is collected. I’m generating the storyboard now..."

        # Apply follow-up message if LLM didn't provide content
        if follow_up_message and not response.content:
            if isinstance(response, AIMessage):
                response = AIMessage(
                    content=follow_up_message,
                    tool_calls=response.tool_calls,
                    additional_kwargs=response.additional_kwargs,
                    response_metadata=response.response_metadata
                    if hasattr(response, "response_metadata")
                    else {},
                )
            else:
                response = AIMessage(content=follow_up_message)

        if ui_tool_calls:
            if not isinstance(response, AIMessage):
                response = AIMessage(
                    content=response.content or follow_up_message or ""
                )
            # Merge with existing tool calls if any
            existing_tcs = list(response.tool_calls or [])
            response.tool_calls = existing_tcs + ui_tool_calls

        print(f"[DEBUG] gatherer returning Command(goto=supervisor, status={status})")
        logger.info(f"  [GATHERER] Returning to supervisor with status={status}")

        return Command(
            goto="supervisor",
            update={
                "messages": [response],
                "collected_info": new_info,
                "status": status,
                "total_duration": sfloat(
                    new_info.get("duration"), sget(state, "total_duration", 120.0)
                )
                if has_duration
                else sget(state, "total_duration", 120.0),
                "clip_duration": 10.0
                if has_duration
                else sget(state, "clip_duration", None),
            },
        )
    except Exception as e:
        logger.exception(f"  [GATHERER] Node failed: {e}")
        return Command(goto="supervisor", update={"error": str(e), "status": "failed"})


async def planner_node(state: AgentState):
    """
    Equivalent to CrewAI's Optimize + Plan + Review tasks.
    Generates the initial storyboard JSON.
    """
    # Ensure run_id exists in state
    run_id = sget(state, "run_id")
    if not run_id or run_id == "unknown":
        # Try to find it in config if possible, or generate a new one
        run_id = str(uuid.uuid4())
        print(
            f"[WARN] planner_node: run_id was missing or unknown. Generated new: {run_id}"
        )

    print(
        f"[DEBUG] planner_node invoked for run_id={run_id}, status={sget(state, 'status', 'none')}"
    )

    collected_info = sget(state, "collected_info", {}) or {}

    # ── 解析叙事结构 ──
    narrative_structure = None
    try:
        from src.creative_agent import get_narrative_for_template, NARRATIVE_STRUCTURES

        template_id = collected_info.get("template_id")
        video_type = collected_info.get("video_type", "")
        if template_id:
            narrative_structure = get_narrative_for_template(template_id)
        elif video_type:
            # 根据视频类型推断叙事结构
            _vtype_to_narrative = {
                "产品宣传视频": "product_showcase",
                "产品演示视频": "product_showcase",
                "美妆种草视频": "beauty_review",
                "服饰穿搭视频": "product_showcase",
                "美食展示视频": "food_showcase",
                "3C数码评测视频": "tech_review",
                "家居好物视频": "lifestyle",
                "品牌故事视频": "brand_story",
                "知识科普视频": "knowledge_edu",
                "搞笑段子视频": "funny_skit",
                "旅行Vlog": "travel_vlog",
                "教程视频": "tutorial",
            }
            ns_key = _vtype_to_narrative.get(video_type)
            if ns_key:
                narrative_structure = NARRATIVE_STRUCTURES.get(ns_key)
        if narrative_structure:
            logger.info(
                f"  [PLANNER] Using narrative structure: {narrative_structure.get('name')}"
            )
    except Exception as e:
        logger.warning(f"  [PLANNER] Failed to load narrative structure: {e}")

    try:
        print(
            f"[DEBUG] planner: Calling plan_storyboard_impl with theme='{collected_info.get('theme')}'"
        )
        storyboard_json = await plan_storyboard_impl(
            goal=collected_info.get("theme", sget(state, "goal", "New Video")),
            styles=collected_info.get("style", sget(state, "styles", [])),
            total_duration=sfloat(
                collected_info.get("duration"),
                sget(state, "total_duration", 120.0) or 120.0,
            ),
            num_clips=sget(state, "num_clips", 4) or 4,
            run_id=run_id,
            collected_info=collected_info,
            narrative_structure=narrative_structure,
        )

        print("[DEBUG] planner: plan_storyboard_impl returned. Parsing JSON...")
        storyboard = json.loads(storyboard_json)
        print(
            f"[DEBUG] planner: Storyboard parsed successfully, {len(storyboard.get('scenes', []))} scenes."
        )

        # Emit a tool call for CopilotKit to render the storyboard
        tool_call = {
            "name": "plan_storyboard",
            "args": {"storyboard": storyboard},
            "id": "call_" + str(uuid.uuid4()),
        }

        return {
            "storyboard": storyboard,
            "status": "visualizing",
            "thoughts": "Storyboard generated. Preparing preview frames.",
            "loop_count": (sget(state, "loop_count", 0) or 0) + 1,
            "messages": [
                AIMessage(
                    content="I’ve prepared a storyboard. Generating preview frames now, please wait...",
                )
            ],
        }
    except Exception as e:
        logger.error(f"  [PLANNING] Planner node failed: {e}")
        return {"error": str(e), "status": "failed"}


async def _resolve_pipeline(state: AgentState):
    """
    Resolve the pipeline for this run.

    Pipeline selection priority:
    1. Already selected in state (from earlier node)
    2. pipeline_hint from template selection (via collected_info)
    3. Automatic selection via SkillSelector scoring

    Returns:
        (pipeline_name, t2i_skill_name, i2v_skill_name) or (None, None, None)
    """
    selected_pipeline_name = sget(state, "selected_pipeline")
    selected_image_skill = sget(state, "selected_image_skill")
    selected_i2v_skill = sget(state, "selected_i2v_skill")

    if selected_pipeline_name and selected_image_skill:
        logger.info(
            f"  [PIPELINE] Pre-selected: {selected_pipeline_name} (t2i={selected_image_skill})"
        )
        return selected_pipeline_name, selected_image_skill, selected_i2v_skill

    collected_info = sget(state, "collected_info", {}) or {}
    orientation_raw = collected_info.get("orientation", "landscape")
    if isinstance(orientation_raw, str):
        if "\u7ad6" in orientation_raw or "vertical" in orientation_raw.lower():
            orientation = "portrait"
        else:
            orientation = "landscape"
    else:
        orientation = "landscape"

    # ── Priority 2: Use pipeline_hint from template config ──
    pipeline_hint = collected_info.get("pipeline_hint")
    if pipeline_hint:
        try:
            from src.skills.registry import get_skills_registry

            registry = await get_skills_registry()
            hinted_pipeline = registry.get_pipeline(pipeline_hint)
            if hinted_pipeline and hinted_pipeline.is_enabled:
                logger.info(
                    f"  [PIPELINE] Using template hint: {hinted_pipeline.name} "
                    f"(t2i={hinted_pipeline.t2i_skill_name}, i2v={hinted_pipeline.i2v_skill_name})"
                )
                return (
                    hinted_pipeline.name,
                    hinted_pipeline.t2i_skill_name,
                    hinted_pipeline.i2v_skill_name,
                )
            else:
                logger.info(
                    f"  [PIPELINE] Hint '{pipeline_hint}' not available, falling back to auto-select"
                )
        except Exception as e:
            logger.warning(f"  [PIPELINE] Hint resolution failed: {e}")

    # ── Priority 3: Automatic selection via SkillSelector ──
    try:
        from src.skills import get_skill_selector

        selector = await get_skill_selector()
        pipelines = await selector.select_pipeline_with_fallback(
            requirements={
                "duration": 10,
                "requires_image": True,
                "orientation": orientation,
            },
            max_fallbacks=3,
        )
        if pipelines:
            p = pipelines[0]
            logger.info(
                f"  [PIPELINE] Auto-resolved: {p.name} (t2i={p.t2i_skill_name}, i2v={p.i2v_skill_name})"
            )
            return p.name, p.t2i_skill_name, p.i2v_skill_name
    except Exception as e:
        logger.warning(f"  [PIPELINE] Auto-resolution failed: {e}")

    return None, None, None


async def _qwen_product_batch_t2i(
    product_image_url: str, prompt: str, timeout: int = 600
):
    """
    Qwen Product pipeline: 一次性批量生成分镜头图片和描述。

    Returns:
        (image_urls: List[str], descriptions: List[str])
    """
    import httpx as _httpx
    from src.runninghub_client import RunningHubClient

    client = RunningHubClient(os.getenv("RUNNINGHUB_API_KEY"))
    t2i_workflow_id = os.getenv(
        "RUNNINGHUB_QWEN_STORYBOARD_WORKFLOW_ID", "2021433434782044162"
    )

    # Upload product image
    image_ref = product_image_url
    if product_image_url.startswith("http"):
        try:
            async with _httpx.AsyncClient(timeout=60) as hc:
                resp = await hc.get(product_image_url)
                if resp.status_code == 200 and resp.content:
                    fname = product_image_url.split("/")[-1] or "product.png"
                    image_ref = await client.upload_bytes(
                        resp.content, fname, file_type="input"
                    )
                    logger.info(f"  [BATCH_T2I] Uploaded product image: {image_ref}")
        except Exception as e:
            logger.warning(f"  [BATCH_T2I] Upload failed, using raw URL: {e}")

    # Submit
    node_info_list = [
        {"nodeId": "74", "fieldName": "image", "fieldValue": image_ref},
        {"nodeId": "103", "fieldName": "text", "fieldValue": prompt},
    ]
    task_id = await client.create_task(t2i_workflow_id, node_info_list)
    logger.info(f"  [BATCH_T2I] Task submitted: {task_id}")

    # Poll
    poll_interval = 5
    max_iters = timeout // poll_interval
    for i in range(max_iters):
        status = await client.get_status(task_id)
        if i % 12 == 0:
            logger.info(
                f"  [BATCH_T2I] Task {task_id}: status={status}, elapsed={i * poll_interval}s"
            )
        if status == "SUCCESS":
            outputs = await client.get_outputs(task_id)
            break
        elif status in ("FAILED", "ERROR"):
            raise RuntimeError(f"T2I 批量任务失败: task_id={task_id}")
        await asyncio.sleep(poll_interval)
    else:
        raise RuntimeError(f"T2I 批量任务超时: task_id={task_id}")

    # Parse outputs
    image_urls = []
    desc_text = None
    for item in outputs:
        url = None
        for field in ("fileUrl", "url", "ossUrl", "value"):
            val = item.get(field)
            if val and isinstance(val, str) and val.startswith("http"):
                url = val.strip()
                break
        if not url:
            continue
        url_path = url.split("?")[0].lower()
        file_type = (item.get("fileType") or "").lower()
        if file_type in ("png", "jpg", "jpeg", "webp") or any(
            url_path.endswith(e) for e in (".png", ".jpg", ".jpeg", ".webp")
        ):
            image_urls.append(url)
        elif file_type in ("txt", "json") or any(
            url_path.endswith(e) for e in (".txt", ".json")
        ):
            try:
                async with _httpx.AsyncClient(timeout=30) as hc:
                    r = await hc.get(url)
                    if r.status_code == 200:
                        desc_text = r.text
            except Exception:
                pass

    # Parse descriptions
    descriptions = []
    if desc_text:
        # Split by "Next Scene:" blocks
        parts = desc_text.split("Next Scene:")
        for p in parts:
            p = p.strip()
            if p:
                descriptions.append(p)
    # Pad if needed
    while len(descriptions) < len(image_urls):
        descriptions.append(f"产品展示场景 {len(descriptions) + 1}")

    logger.info(
        f"  [BATCH_T2I] Result: {len(image_urls)} images, {len(descriptions)} descriptions"
    )
    await client.aclose()
    return image_urls, descriptions


async def image_gen_node(state: AgentState):
    """
    Generates preview images for each scene using the product reference image.

    Two modes:
    - qwen_product pipeline: single batch call returns all images + descriptions
    - Legacy/sora2 pipeline: per-scene generate_scene calls
    """
    run_id = sget(state, "run_id", "unknown")
    logger.info(f"\n>>>> [AGENT: VISUALIZER] run_id={run_id} <<<<")

    if not sget(state, "image_control", True):
        print(
            "[DEBUG] visualizer: image_control is False, emitting tool call without new images."
        )
        storyboard = sget(state, "storyboard", {}) or {}
        tool_call = {
            "name": "plan_storyboard",
            "args": {"storyboard": storyboard},
            "id": "call_" + str(uuid.uuid4()),
        }
        return {
            "status": "awaiting_approval",
            "thoughts": "Storyboard generated. Please review and start production.",
            "messages": [
                AIMessage(
                    content="Your storyboard is ready. Please review the details and start production.",
                    tool_calls=[tool_call],
                )
            ],
        }

    try:
        storyboard = sget(state, "storyboard", {}) or {}
        scenes = storyboard.get("scenes", [])
        collected_info = sget(state, "collected_info", {}) or {}
        product_image_url = collected_info.get("product_image", "")

        # Resolve pipeline
        pipeline_name, t2i_skill, i2v_skill = await _resolve_pipeline(state)

        # ──────────────────────────────────────────────────────────
        # PATH A: qwen_product — batch T2I (single RunningHub call)
        # ──────────────────────────────────────────────────────────
        if pipeline_name == "qwen_product":
            logger.info(
                f"  [VISUALIZER] Qwen product batch T2I, ref image: {product_image_url}"
            )

            # Build batch prompt
            batch_prompt = collected_info.get("t2i_prompt", "")
            if not batch_prompt:
                topic = collected_info.get("topic", "产品展示")
                style = collected_info.get("style", "")
                num_scenes = max(len(scenes), 6)
                batch_prompt = (
                    f"这是一部{topic}广告宣传片，参考图片，帮我生成{num_scenes}张"
                    f"产品广告宣传片分镜头，不同运镜和角度，不同的视角和景别。"
                )
                if style:
                    batch_prompt += f" 风格: {style}"
            logger.info(f"  [VISUALIZER] Batch T2I prompt: {batch_prompt[:100]}...")

            image_urls, descriptions = await _qwen_product_batch_t2i(
                product_image_url=product_image_url,
                prompt=batch_prompt,
            )

            if not image_urls:
                return {
                    "storyboard": storyboard,
                    "status": "awaiting_approval",
                    "interaction_type": "single_choice",
                    "options": ["Retry"],
                    "thoughts": "Batch T2I returned no images.",
                    "messages": [
                        AIMessage(content="分镜图片生成失败，未返回任何图片。请重试。")
                    ],
                    "run_id": run_id,
                    "selected_pipeline": pipeline_name,
                    "selected_image_skill": t2i_skill,
                    "selected_i2v_skill": i2v_skill,
                }

            # Rebuild storyboard scenes to match batch output
            new_scenes = []
            for idx, img_url in enumerate(image_urls):
                desc = (
                    descriptions[idx]
                    if idx < len(descriptions)
                    else f"产品展示场景 {idx + 1}"
                )
                new_scenes.append(
                    {
                        "scene_idx": idx + 1,
                        "narration": desc,
                        "keyframes": {"in": img_url},
                        "visual_status": "success",
                    }
                )
            storyboard["scenes"] = new_scenes
            storyboard["_batch_descriptions"] = descriptions
            logger.info(
                f"  [VISUALIZER] Rebuilt storyboard: {len(new_scenes)} scenes from batch T2I"
            )

        # ──────────────────────────────────────────────────────────
        # PATH B: Legacy / sora2 — per-scene generate_scene
        # ──────────────────────────────────────────────────────────
        else:
            ip = get_image_provider()
            if pipeline_name:
                logger.info(
                    f"  [VISUALIZER] Pipeline bound: {pipeline_name} (t2i={t2i_skill}, i2v={i2v_skill})"
                )
            else:
                logger.info(f"  [VISUALIZER] Using legacy image provider (no pipeline)")

            logger.info(
                f"  [VISUALIZER] Rendering {len(scenes)} scenes with reference image: {product_image_url}"
            )

            for i, scene in enumerate(scenes):
                scene_id = scene.get("scene_idx", i + 1)
                if not scene.get("keyframes", {}).get("in"):
                    desc = scene.get("narration") or scene.get("desc", "")
                    print(
                        f"[DEBUG] visualizer: Generating image for Scene {scene_id} - '{desc[:30]}...'"
                    )
                    try:
                        result = await ip.generate_scene(
                            image_url=product_image_url, text=desc
                        )
                        if isinstance(result, dict):
                            img_url = result.get("image_url")
                        else:
                            img_url = result

                        if img_url:
                            if "keyframes" not in scene:
                                scene["keyframes"] = {}
                            scene["keyframes"]["in"] = img_url
                            scene["visual_status"] = "success"
                            logger.info(
                                f"  [VISUALIZER] Scene {scene.get('scene_idx')} generated: {img_url}"
                            )
                        else:
                            scene["visual_status"] = "failed"
                            scene["visual_error"] = "No image URL returned"
                            logger.warning(
                                f"  [VISUALIZER] Scene {scene.get('scene_idx')} returned no image URL"
                            )
                    except Exception as e:
                        scene["visual_status"] = "failed"
                        scene["visual_error"] = str(e)
                        print(f"[ERROR] visualizer: Scene {scene_id} exception -> {e}")
                        logger.warning(f"  [VISUALIZER] Failed scene {scene_id}: {e}")
                else:
                    print(
                        f"[DEBUG] visualizer: Scene {scene_id} already has an image, skipping."
                    )

        print("[DEBUG] visualizer_node completed successfully.")

        # Count failures
        scenes = storyboard.get("scenes", [])
        failed_count = sum(1 for s in scenes if s.get("visual_status") == "failed")
        success_count = len(scenes) - failed_count

        if failed_count > 0:
            print(f"[DEBUG] visualizer: {failed_count} scenes failed.")
            msg_content = f"Storyboard preview rendering partially failed. Success: {success_count}, failed: {failed_count}. Please retry the failed scenes to continue."
            return {
                "storyboard": storyboard,
                "status": "awaiting_approval",
                "interaction_type": "single_choice",
                "options": ["Retry failed scenes"],
                "thoughts": f"Storyboard rendering had failures ({failed_count}). All failed scenes must be retried.",
                "messages": [AIMessage(content=msg_content)],
                "run_id": run_id,
                "selected_pipeline": pipeline_name,
                "selected_image_skill": t2i_skill,
                "selected_i2v_skill": i2v_skill,
            }

        tool_call = {
            "name": "plan_storyboard",
            "args": {"storyboard": storyboard},
            "id": "call_" + str(uuid.uuid4()),
        }

        msg_content = "Preview frames are ready. Please confirm the storyboard, then click the button below to start production."
        thoughts = f"Preview frames rendered ({len(scenes)} scenes). Please confirm and click Start production."

        return {
            "storyboard": storyboard,
            "status": "awaiting_approval",
            "thoughts": thoughts,
            "messages": [AIMessage(content=msg_content, tool_calls=[tool_call])],
            "run_id": run_id,
            "selected_pipeline": pipeline_name,
            "selected_image_skill": t2i_skill,
            "selected_i2v_skill": i2v_skill,
        }
    except Exception as e:
        logger.error(f"  [VISUALIZER] Node failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


async def task_prepper_node(state: AgentState):
    """
    Prepare video tasks from storyboard scenes.

    Two modes:
    - qwen_product pipeline: pair adjacent images as first_frame / last_frame
      (N images -> N-1 video tasks)
    - Legacy/sora2: one video task per scene (existing logic)
    """
    try:
        run_id = sget(state, "run_id", "unknown")
        logger.info(f"\n>>>> [WORKFLOW: TASK_PREP] run_id={run_id} <<<<")
        storyboard = sget(state, "storyboard", {}) or {"scenes": []}
        scenes = storyboard.get("scenes", [])
        selected_pipeline = sget(state, "selected_pipeline")
        orientation = (sget(state, "collected_info", {}) or {}).get("orientation")

        # ── PATH A: qwen_product — first/last frame pairing ──
        if selected_pipeline == "qwen_product" and len(scenes) >= 2:
            descriptions = storyboard.get("_batch_descriptions", [])
            video_tasks = []
            for i in range(len(scenes) - 1):
                first_scene = scenes[i]
                last_scene = scenes[i + 1]
                first_url = first_scene.get("keyframes", {}).get("in", "")
                last_url = last_scene.get("keyframes", {}).get("in", "")
                # Use description for the video segment (maps to first scene's narration)
                desc = (
                    descriptions[i]
                    if i < len(descriptions)
                    else first_scene.get("narration", f"产品展示场景 {i + 1}")
                )
                task = {
                    "idx": i + 1,
                    "task_idx": i + 1,
                    "prompt": desc,
                    "first_frame_url": first_url,
                    "last_frame_url": last_url,
                    "duration": 5,
                    "run_id": run_id,
                    "pipeline": "qwen_product",
                }
                if orientation:
                    task["orientation"] = orientation
                video_tasks.append(task)

            logger.info(
                f"  [TASK_PREP] qwen_product: {len(scenes)} images -> {len(video_tasks)} first/last frame pairs"
            )
            print(
                f"[DEBUG] task_prepper: Created {len(video_tasks)} first/last-frame video tasks (qwen_product)."
            )
            return {
                "video_tasks": video_tasks,
                "status": "generating",
                "run_id": run_id,
            }

        # ── PATH B: Legacy — one task per scene ──
        storyboard_json = json.dumps(storyboard)
        total_duration = sget(state, "total_duration", 120.0)
        print(f"[DEBUG] task_prepper: Preparing {len(scenes)} scenes into tasks.")
        video_tasks_json = merge_storyboards_to_video_tasks_impl(
            storyboard_json, run_id, total_duration
        )
        video_tasks = (
            json.loads(video_tasks_json)
            if isinstance(video_tasks_json, str)
            else video_tasks_json
        )
        if orientation:
            for t in video_tasks:
                if isinstance(t, dict):
                    t["orientation"] = orientation
        print(f"[DEBUG] task_prepper: Created {len(video_tasks)} video tasks.")
        return {"video_tasks": video_tasks, "status": "generating", "run_id": run_id}
    except Exception as e:
        logger.error(f"  [TASK_PREP] Node failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


async def skill_selector_node(state: AgentState):
    """
    Select an optimal **pipeline** for video generation tasks.

    A pipeline bundles co-dependent T2I + I2V skills that MUST be used together.
    For example, the "sora2" pipeline pairs Qwen image generation with Sora2 video
    generation. This prevents non-sora2 workflows from accidentally referencing
    sora2-specific image/video skills.

    This node runs after task_prepper and before executor.
    It writes both `selected_pipeline` and `selected_image_skill` / `selected_i2v_skill`
    into state so that downstream nodes (image_gen_node, executor_node) use the
    correct paired skills.
    """
    try:
        run_id = sget(state, "run_id", "unknown")
        logger.info(f"\n>>>> [WORKFLOW: SKILL_SELECTOR] run_id={run_id} <<<<")

        video_tasks = sget(state, "video_tasks", []) or []
        collected_info = sget(state, "collected_info", {}) or {}

        if not video_tasks:
            logger.warning("  [SKILL_SELECTOR] No video tasks to process")
            return {"status": "generating", "run_id": run_id}

        # Determine requirements from state
        orientation_raw = collected_info.get("orientation", "landscape")
        if isinstance(orientation_raw, str):
            if "竖" in orientation_raw or "vertical" in orientation_raw.lower():
                orientation = "portrait"
            else:
                orientation = "landscape"
        else:
            orientation = "landscape"

        # Get first task's duration as reference
        first_task = video_tasks[0] if video_tasks else {}
        duration = first_task.get("duration", 10)

        requirements = {
            "duration": duration,
            "requires_image": True,
        }
        if orientation:
            requirements["orientation"] = orientation

        # --- Pipeline-based selection (preferred) ---
        try:
            from src.skills import get_skill_selector

            selector = await get_skill_selector()
            pipelines = await selector.select_pipeline_with_fallback(
                requirements=requirements,
                max_fallbacks=3,
            )

            if pipelines:
                primary = pipelines[0]
                logger.info(
                    f"  [SKILL_SELECTOR] Selected pipeline: {primary.name} "
                    f"(t2i={primary.t2i_skill_name}, i2v={primary.i2v_skill_name})"
                )

                # Build fallback I2V skill chain from pipelines
                i2v_skill_chain = [
                    p.i2v_skill_name for p in pipelines if p.i2v_skill_name
                ]

                # Annotate each video task with the skill chain
                for task in video_tasks:
                    task["selected_skills"] = i2v_skill_chain
                    task["current_skill_index"] = 0

                num_tasks = len(video_tasks)
                engine_msg = (
                    f"🎬 Using **{primary.display_name}** to generate {num_tasks} clips. "
                    f"This may take a few minutes per clip."
                )

                return {
                    "video_tasks": video_tasks,
                    "selected_pipeline": primary.name,
                    "selected_skills": i2v_skill_chain,
                    "selected_image_skill": primary.t2i_skill_name,
                    "selected_i2v_skill": primary.i2v_skill_name,
                    "status": "generating",
                    "run_id": run_id,
                    "messages": [AIMessage(content=engine_msg)],
                }
            else:
                logger.warning(
                    "  [SKILL_SELECTOR] No pipelines available, falling back to legacy provider"
                )

        except ImportError as e:
            logger.warning(
                f"  [SKILL_SELECTOR] Skills module not available: {e}, using legacy provider"
            )
        except Exception as e:
            logger.error(
                f"  [SKILL_SELECTOR] Error selecting pipeline: {e}, using legacy provider"
            )

        # --- Fallback: use legacy provider (no pipeline/skill selection) ---
        num_tasks = len(video_tasks)
        fallback_msg = f"🎬 Starting video generation for {num_tasks} clips. This may take a few minutes per clip."
        return {
            "video_tasks": video_tasks,
            "status": "generating",
            "run_id": run_id,
            "messages": [AIMessage(content=fallback_msg)],
        }

    except Exception as e:
        logger.error(f"  [SKILL_SELECTOR] Node failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


RUNNINGHUB_MAX_CONCURRENT = int(
    os.getenv("RUNNINGHUB_MAX_CONCURRENT", "2")
)  # RunningHub 全局并发任务上限


def _is_uuid(val):
    """Check if a value is a valid UUID string."""
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


async def _executor_submit_one_task(
    task: dict,
    run_id: str,
    state: AgentState,
    selected_skills: list,
    registry,
    provider,
    supabase_client,
) -> dict:
    """
    Submit a single video generation task (used by both sequential and concurrent paths).

    Returns a dict with keys: task_idx, status, task_id, skill_name, error.
    """
    prompt = task.get("prompt") or task.get("desc") or ""
    idx = task.get("idx") or task.get("task_idx") or task.get("scene_idx")
    duration = task.get("duration") or task.get("total_duration") or 10.0

    # ── Extract image references ──
    # For qwen_product: first_frame_url + last_frame_url
    # For legacy/sora2: single image_url
    first_frame_url = task.get("first_frame_url", "")
    last_frame_url = task.get("last_frame_url", "")
    img_url = task.get("image_url") or task.get("ref_img") or ""
    if not img_url and isinstance(task.get("keyframes"), dict):
        img_url = task.get("keyframes", {}).get("in", "")

    # Orientation
    orientation_raw = (sget(state, "collected_info", {}) or {}).get("orientation")
    orientation = None
    if isinstance(orientation_raw, str):
        lower = orientation_raw.lower()
        if "\u6a2a" in orientation_raw or "horizontal" in lower:
            orientation = "landscape"
        elif "\u7ad6" in orientation_raw or "vertical" in lower:
            orientation = "portrait"

    # DB dedup check
    existing = (
        supabase_client.table("autoviralvid_video_tasks")
        .select("status")
        .eq("run_id", run_id)
        .eq("clip_idx", idx)
        .execute()
    )
    if existing.data and existing.data[0].get("status") == "succeeded":
        logger.info(f"  [EXECUTOR] Clip {idx} already succeeded, skipping.")
        return {
            "task_idx": idx,
            "status": "succeeded",
            "task_id": None,
            "skill_name": None,
            "error": None,
            "skipped": True,
        }

    if existing.data and existing.data[0].get("status") == "failed":
        logger.info(f"  [EXECUTOR] Clip {idx} was failed, retrying...")
        supabase_client.table("autoviralvid_video_tasks").delete().eq(
            "run_id", run_id
        ).eq("clip_idx", idx).execute()

    log_img = (
        first_frame_url[:40] if first_frame_url else img_url[:40] if img_url else "none"
    )
    logger.info(
        f"  [EXECUTOR] Submitting clip {idx}: prompt='{prompt[:50]}...', img='{log_img}'"
    )

    result = None
    skill_name = None
    skill_id = None
    execution_id = None
    execution_start_time = datetime.utcnow()

    use_skills = bool(selected_skills) and registry is not None
    if use_skills:
        task_skills = task.get("selected_skills", selected_skills)
        current_skill_index = task.get("current_skill_index", 0)
        if current_skill_index < len(task_skills):
            skill_name = task_skills[current_skill_index]
            skill = registry.get_skill(skill_name)
            if skill:
                skill_id = skill.id
                adapter = registry.create_adapter(skill)
                if adapter:
                    from src.skills import SkillExecutionRequest

                    # Build params — include first/last frame if present
                    params = {
                        "prompt": prompt,
                        "duration": int(duration),
                        "orientation": orientation,
                    }
                    if first_frame_url and last_frame_url:
                        params["first_frame_url"] = first_frame_url
                        params["last_frame_url"] = last_frame_url
                    else:
                        params["image_url"] = img_url

                    # Digital human params: audio, voice mode, voice text
                    if task.get("audio_url"):
                        params["audio_url"] = task["audio_url"]
                    if task.get("voice_mode") is not None:
                        params["voice_mode"] = task["voice_mode"]
                    if task.get("voice_text"):
                        params["voice_text"] = task["voice_text"]

                    request = SkillExecutionRequest(
                        skill_id=skill.id,
                        run_id=run_id,
                        params=params,
                        clip_idx=idx,
                    )

                    # Record execution start
                    try:
                        exec_insert_data = {
                            "run_id": run_id,
                            "input_params": {
                                k: (v[:500] if isinstance(v, str) else v)
                                for k, v in params.items()
                            },
                            "status": "pending",
                            "created_at": execution_start_time.isoformat(),
                        }
                        if _is_uuid(skill_id):
                            exec_insert_data["skill_id"] = skill_id
                        exec_record = (
                            supabase_client.table("autoviralvid_skill_executions")
                            .insert(exec_insert_data)
                            .execute()
                        )
                        if exec_record.data:
                            execution_id = exec_record.data[0].get("id")
                    except Exception as e:
                        logger.warning(
                            f"  [EXECUTOR] Failed to record skill execution: {e}"
                        )

                    # Retry loop for TASK_QUEUE_MAXED
                    max_queue_retries = 40  # 40 * 30s = 20 min max wait
                    for _retry in range(max_queue_retries):
                        try:
                            exec_result = await adapter.execute(request)
                            # Check for queue-full error returned as failed status
                            if (
                                exec_result.status == "failed"
                                and exec_result.error
                                and "TASK_QUEUE_MAXED" in exec_result.error
                            ):
                                if _retry < max_queue_retries - 1:
                                    if _retry % 4 == 0:
                                        logger.warning(
                                            f"  [EXECUTOR] Clip {idx}: queue full, waiting 30s (retry {_retry + 1}/{max_queue_retries})"
                                        )
                                    await asyncio.sleep(30)
                                    continue
                            result = {
                                "status": exec_result.status
                                if exec_result.status != "submitted"
                                else "pending",
                                "task_id": exec_result.task_id,
                                "error": exec_result.error,
                            }
                            logger.info(
                                f"  [EXECUTOR] Skill {skill_name} result: {result['status']}"
                            )
                            if execution_id:
                                try:
                                    supabase_client.table(
                                        "autoviralvid_skill_executions"
                                    ).update(
                                        {
                                            "task_id": exec_result.task_id,
                                            "status": "submitted"
                                            if result["status"] == "pending"
                                            else result["status"],
                                        }
                                    ).eq("id", execution_id).execute()
                                except Exception as e:
                                    logger.warning(
                                        f"  [EXECUTOR] Failed to update skill execution: {e}"
                                    )
                            break
                        except Exception as e:
                            err_str = str(e)
                            if (
                                "TASK_QUEUE_MAXED" in err_str
                                and _retry < max_queue_retries - 1
                            ):
                                if _retry % 4 == 0:
                                    logger.warning(
                                        f"  [EXECUTOR] Clip {idx}: queue full (exception), waiting 30s (retry {_retry + 1}/{max_queue_retries})"
                                    )
                                await asyncio.sleep(30)
                                continue
                            logger.error(f"  [EXECUTOR] Skill {skill_name} failed: {e}")
                            result = {"status": "failed", "error": err_str}
                            if execution_id:
                                try:
                                    duration_ms = int(
                                        (
                                            datetime.utcnow() - execution_start_time
                                        ).total_seconds()
                                        * 1000
                                    )
                                    supabase_client.table(
                                        "autoviralvid_skill_executions"
                                    ).update(
                                        {
                                            "status": "failed",
                                            "error_message": err_str[:1000],
                                            "duration_ms": duration_ms,
                                        }
                                    ).eq("id", execution_id).execute()
                                except Exception as update_err:
                                    logger.warning(
                                        f"  [EXECUTOR] Failed to record execution failure: {update_err}"
                                    )
                            break

    # Fallback to legacy provider
    if result is None:
        try:
            result = await provider.generate(
                prompt=prompt,
                image_url=img_url or first_frame_url,
                duration=int(duration),
                orientation=orientation,
            )
        except Exception as e:
            logger.error(f"  [EXECUTOR] Legacy provider failed: {e}", exc_info=True)
            result = {"status": "failed", "error": str(e)}

    # Record to DB
    if result.get("status") != "failed":
        task_data = {
            "run_id": run_id,
            "clip_idx": idx,
            "prompt": prompt,
            "ref_img": first_frame_url or img_url,
            "duration": int(duration),
            "status": "submitted",
            "provider_task_id": result.get("task_id"),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        if skill_name:
            task_data["skill_name"] = skill_name
        if skill_id and _is_uuid(skill_id):
            task_data["skill_id"] = skill_id
        try:
            supabase_client.table("autoviralvid_video_tasks").insert(
                task_data
            ).execute()
        except Exception as db_err:
            logger.warning(
                f"  [EXECUTOR] Failed to record task to DB (non-fatal): {db_err}"
            )

    return {
        "task_idx": idx,
        "status": result.get("status"),
        "task_id": result.get("task_id"),
        "skill_name": skill_name,
        "error": result.get("error"),
    }


async def executor_node(state: AgentState):
    """
    Execute video generation tasks using Skills or legacy provider.

    For qwen_product pipeline: uses sliding-window concurrency (max 2 concurrent
    RunningHub tasks) and passes first_frame_url/last_frame_url to the I2V adapter.
    For other pipelines: sequential submission as before.
    """
    try:
        run_id = sget(state, "run_id", "unknown")
        selected_pipeline = sget(state, "selected_pipeline")
        logger.info(
            f"\n>>>> [WORKFLOW: EXECUTOR] run_id={run_id}, pipeline={selected_pipeline} <<<<"
        )

        video_tasks = sget(state, "video_tasks", []) or []
        selected_skills = sget(state, "selected_skills", [])

        from supabase import create_client

        supabase_client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY"),
        )

        use_skills = bool(selected_skills)
        if use_skills:
            logger.info(
                f"  [EXECUTOR] Using Skills system with chain: {selected_skills}"
            )
        else:
            logger.info(f"  [EXECUTOR] Using legacy provider (no skills selected)")

        provider = get_video_provider()
        registry = None
        if use_skills:
            try:
                from src.skills import get_skills_registry, SkillExecutionRequest

                registry = await get_skills_registry()
            except ImportError:
                logger.warning(
                    "  [EXECUTOR] Skills module not available, using legacy provider"
                )
                use_skills = False

        clip_results = []

        # ── Sequential submission (default for legacy/sora2) ──
        for task in video_tasks:
            cr = await _executor_submit_one_task(
                task=task,
                run_id=run_id,
                state=state,
                selected_skills=selected_skills,
                registry=registry,
                provider=provider,
                supabase_client=supabase_client,
            )
            clip_results.append(cr)

            # For qwen_product: add small delay between submissions to avoid
            # overwhelming RunningHub's concurrent task limit
            if selected_pipeline == "qwen_product" and cr.get("status") != "failed":
                await asyncio.sleep(2)

        return {"clip_results": clip_results, "status": "processing", "run_id": run_id}

    except Exception as e:
        logger.error(f"  [EXECUTOR] Node failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


async def poller_node(state: AgentState):
    """
    One-shot status check for video generation tasks.

    The actual polling is handled by SupabaseVideoTaskQueue._worker_loop()
    which runs in the background every 20 seconds. This node only checks current
    database state and returns immediately, avoiding blocking the LangGraph workflow.
    """
    try:
        run_id = sget(state, "run_id", "unknown")
        logger.info(f"\n>>>> [WORKFLOW: POLLER] run_id={run_id} (one-shot check) <<<<")

        if sget(state, "status", None) == "ready_to_stitch":
            return {}

        from supabase import create_client

        supabase_client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY"),
        )

        # One-shot database query - no polling loop
        res = (
            supabase_client.table("autoviralvid_video_tasks")
            .select("*")
            .eq("run_id", run_id)
            .execute()
        )
        db_tasks = res.data or []

        if not db_tasks:
            # No tasks found - check if executor failed to submit
            clip_results = sget(state, "clip_results", [])
            submission_failed = (
                all(r.get("status") == "failed" for r in clip_results)
                if clip_results
                else False
            )

            if submission_failed or (
                not clip_results and sget(state, "video_tasks", [])
            ):
                logger.warning(
                    f"  [POLLER] All submissions failed in executor for run_id={run_id}"
                )
                return {
                    "status": "awaiting_stitch_approval",
                    "interaction_type": "single_choice",
                    "options": ["Retry failed clips"],
                    "thoughts": "All video generation submissions failed; workflow halted.",
                    "messages": [
                        AIMessage(
                            content="Video generation submission failed (service may be unavailable). Please click below to retry."
                        )
                    ],
                    "run_id": run_id,
                }

            # Tasks may not be in DB yet - return processing status and let frontend poll
            logger.info(
                f"  [POLLER] No tasks in DB yet for run_id={run_id}, returning processing status"
            )
            return {
                "status": "processing",
                "thoughts": "Tasks submitted; waiting for processing.",
                "messages": [
                    AIMessage(
                        content="Video tasks submitted and generating. The backend will poll progress automatically. You can refresh later to see the latest status."
                    )
                ],
                "run_id": run_id,
            }

        # Count task statuses
        succeeded_count = sum(1 for t in db_tasks if t.get("status") == "succeeded")
        failed_count = sum(1 for t in db_tasks if t.get("status") == "failed")
        pending_count = sum(
            1
            for t in db_tasks
            if t.get("status") in ("pending", "processing", "submitted")
        )
        total_count = len(db_tasks)

        all_done = pending_count == 0
        any_failed = failed_count > 0

        logger.info(
            f"  [POLLER] Task status: total={total_count}, succeeded={succeeded_count}, failed={failed_count}, pending={pending_count}"
        )

        # Build per-clip status detail for rich feedback
        clip_lines = []
        for t in sorted(db_tasks, key=lambda x: x.get("clip_idx", 0)):
            cidx = t.get("clip_idx", "?")
            st = t.get("status", "unknown")
            icon = {
                "succeeded": "✅",
                "failed": "❌",
                "processing": "⏳",
                "submitted": "🔄",
                "pending": "🕐",
            }.get(st, "❓")
            clip_lines.append(f"{icon} Clip {cidx}: {st}")
        clip_detail = "\n".join(clip_lines)

        if all_done:
            if any_failed:
                logger.warning(
                    f"  [POLLER] {failed_count} clips failed for run_id={run_id}"
                )
                status_text = f"⚠️ {failed_count} of {total_count} clips failed. You can retry them from the editor or click below.\n\n{clip_detail}"
                return {
                    "status": "awaiting_stitch_approval",
                    "interaction_type": "single_choice",
                    "options": ["Retry failed clips"],
                    "thoughts": "Video production had failures; retries are required.",
                    "messages": [AIMessage(content=status_text)],
                    "run_id": run_id,
                }

            # All successful
            logger.info(
                f"  [POLLER] All {total_count} clips succeeded for run_id={run_id}"
            )
            status_text = f"🎉 All {total_count} clips are ready! Click below to stitch them into your final video.\n\n{clip_detail}"
            tool_call = {
                "name": "confirm_video_synthesis",
                "args": {"clips": db_tasks},
                "id": "call_" + str(uuid.uuid4()),
            }
            return {
                "status": "awaiting_stitch_approval",
                "run_id": run_id,
                "thoughts": status_text,
                "messages": [AIMessage(content=status_text, tool_calls=[tool_call])],
            }

        # Still processing - rich progress feedback
        pct = int(succeeded_count / total_count * 100) if total_count else 0
        bar_filled = pct // 10
        bar_empty = 10 - bar_filled
        progress_bar = "█" * bar_filled + "░" * bar_empty
        progress_text = f"🎬 Generating video clips: [{progress_bar}] {succeeded_count}/{total_count} ({pct}%)\n\n{clip_detail}"
        return {
            "status": "processing",
            "thoughts": f"Video progress: {succeeded_count}/{total_count} ({pct}%)",
            "messages": [AIMessage(content=progress_text)],
            "video_tasks": db_tasks,
            "run_id": run_id,
        }
    except Exception as e:
        logger.error(f"  [POLLER] Node failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


async def stitcher_node(state: AgentState):
    try:
        from src.video_stitcher import stitch_videos_for_run

        run_id = sget(state, "run_id", "unknown")
        logger.info(f"\n>>>> [WORKFLOW: STITCHER] run_id={run_id} <<<<")
        final_url = await stitch_videos_for_run(run_id)
        if not final_url:
            raise Exception("Video stitching failed, no output URL produced.")
        return {
            "final_video_url": final_url,
            "final_audio_url": final_url,
            "status": "completed",
            "run_id": run_id,
        }
    except Exception as e:
        logger.error(f"  [STITCHER] Node failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


from src.avatar_agent import avatar_node

# --- Graph Orchestration ---

from langgraph.checkpoint.memory import MemorySaver


def build_video_graph():
    checkpointer = MemorySaver()
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("gatherer", gatherer_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("visualizer", image_gen_node)
    workflow.add_node("task_prepper", task_prepper_node)
    workflow.add_node(
        "skill_selector", skill_selector_node
    )  # NEW: Skills-based selection
    workflow.add_node("executor", executor_node)
    workflow.add_node("poller", poller_node)
    workflow.add_node("stitcher", stitcher_node)
    workflow.add_node("avatar", avatar_node)

    # Set Entry Point
    workflow.set_entry_point("supervisor")

    # Define Edges
    def supervisor_route(state: AgentState):
        status = sget(state, "status", "gathering") or "gathering"
        messages = sget(state, "messages", [])
        last_msg = messages[-1] if messages else None

        print(
            f"[DEBUG] supervisor_route: status={status}, last_msg_type={type(last_msg).__name__}"
        )

        if status == "gathering":
            # If last message is from user, we need to gather info.
            # If last message is from AI, it means gatherer already answered, so we wait for user.
            if isinstance(last_msg, HumanMessage):
                return "gatherer"
            return "end"

        if status == "planning":
            return "planner"

        if status == "visualizing":
            return "visualizer"

        if status == "generating":
            return "task_prepper"

        if status in ["processing", "awaiting_stitch_approval", "ready_to_stitch"]:
            return "poller"

        if status in ["awaiting_approval", "completed", "failed"]:
            return "end"

        return "gatherer"  # Default fallback

    workflow.add_conditional_edges(
        "supervisor",
        supervisor_route,
        {
            "gatherer": "gatherer",
            "planner": "planner",
            "visualizer": "visualizer",
            "task_prepper": "task_prepper",
            "poller": "poller",
            "end": END,
        },
    )

    workflow.add_edge("gatherer", "supervisor")  # gatherer always returns to supervisor
    workflow.add_edge("planner", "supervisor")
    workflow.add_edge("visualizer", "supervisor")

    # Skills-based flow: task_prepper -> skill_selector -> executor
    workflow.add_edge("task_prepper", "skill_selector")
    workflow.add_edge("skill_selector", "executor")
    workflow.add_edge("executor", "supervisor")  # Back to supervisor to route to poller

    def poll_route(state: AgentState):
        """
        Route after poller_node check:
        - ready_to_stitch: proceed to stitcher
        - awaiting_stitch_approval/failed: end workflow, wait for user action
        - processing: end workflow, frontend polls for updates while
                      SupabaseVideoTaskQueue._worker_loop handles background polling
        """
        status = sget(state, "status", "processing")
        if status == "ready_to_stitch":
            return "stitch"
        if status in ("awaiting_stitch_approval", "failed", "processing"):
            return "end"  # Exit workflow; frontend/background worker handles polling
        return "end"  # Default to end to prevent infinite loops

    workflow.add_conditional_edges(
        "poller", poll_route, {"stitch": "stitcher", "end": END}
    )

    workflow.add_edge("stitcher", "avatar")
    workflow.add_edge("avatar", END)

    return workflow.compile(checkpointer=checkpointer)


# --- Integration Helpers ---

_app = None


def get_workflow_app():
    global _app
    if _app is None:
        _app = build_video_graph()
    return _app


async def start_video_generation(payload: Dict[str, Any]):
    """
    Starts or resumes the video generation workflow.
    """
    app = get_workflow_app()
    run_id = payload.get("run_id")
    thread_id = payload.get("thread_id") or f"thread_{run_id}"

    config = {"configurable": {"thread_id": thread_id}}

    # Check if we should resume or start new
    state = await app.aget_state(config)

    if state.values:
        # Resume (User approved the plan)
        logger.info(f"Resuming workflow for {run_id}")
        return await app.ainvoke(None, config)
    else:
        # Start fresh
        logger.info(f"Starting new workflow for {run_id}")
        inputs = {
            "goal": payload.get("goal"),
            "styles": payload.get("styles", []),
            "total_duration": payload.get(
                "total_duration", 120.0
            ),  # Default 2 minutes for 12 scenes
            "num_clips": payload.get("num_clips", 0),
            "image_control": payload.get("image_control", False),
            "use_avatar": payload.get("use_avatar", False),
            "run_id": run_id,
            "thread_id": thread_id,
            "loop_count": 0,
            "collected_info": {},
            "messages": [HumanMessage(content=payload.get("goal") or "")],
        }
        return await app.ainvoke(inputs, config)


async def update_video_generation(run_id: str, thread_id: str, updates: Dict[str, Any]):
    """
    Updates the state of an existing workflow and triggers the updater node.
    """
    app = get_workflow_app()
    config = {"configurable": {"thread_id": thread_id}}

    # Update the state (e.g., modified storyboard)
    await app.aupdate_state(config, updates, as_node="updater")

    # Trigger the workflow to continue from updater
    return await app.ainvoke(None, config)
