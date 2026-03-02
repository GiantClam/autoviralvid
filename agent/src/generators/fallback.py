import logging
from typing import List, Dict, Any, Union
from .base import BaseGenerator

logger = logging.getLogger("workflow")

class MultiGenerator(BaseGenerator):
    """
    A generator that wraps multiple candidate generators and tries them in order.
    Provides automatic fallback logic.
    """
    def __init__(self, generators: List[BaseGenerator]):
        self.generators = generators
        self._active_generator_index = 0

    async def generate(self, **kwargs) -> Dict[str, Any]:
        last_error = "No generators available"
        
        for i, gen in enumerate(self.generators):
            logger.info(f"[MultiGenerator] Trying generator {i+1}/{len(self.generators)}")
            try:
                result = await gen.generate(**kwargs)
                
                if result.get("status") != "failed":
                    # Success or pending, record which one worked by prefixing the task_id
                    # This avoids needing a separate 'task_metadata' column in DB
                    orig_id = result.get("task_id")
                    if orig_id:
                        result["task_id"] = f"{i}:{orig_id}"
                    
                    result["_generator_index"] = i
                    return result
                
                last_error = result.get("error")
                logger.warning(f"[MultiGenerator] Generator {i+1} failed: {last_error}. Falling back...")
            except Exception as e:
                last_error = f"Exception in generator {i+1}: {str(e)}"
                logger.error(f"[MultiGenerator] CRITICAL: Generator {i+1} crashed: {e}", exc_info=True)
                logger.warning(f"[MultiGenerator] Falling back due to crash...")

        return {"status": "failed", "error": f"All generators failed. Last error: {last_error}"}

    async def get_status(self, task_metadata: Union[Dict[str, Any], str]) -> Dict[str, Any]:
        """
        Supports both metadata dict or encoded task_id string "index:task_id".
        """
        try:
            if isinstance(task_metadata, str) and ":" in task_metadata:
                parts = task_metadata.split(":", 1)
                idx = int(parts[0])
                task_id = parts[1]
            elif isinstance(task_metadata, dict):
                idx = task_metadata.get("_generator_index", 0)
                task_id = task_metadata.get("task_id")
            else:
                # Fallback to first generator if format is unknown
                idx = 0
                task_id = str(task_metadata)
            
            if idx >= len(self.generators):
                return {"status": "failed", "error": "Invalid generator index"}
                
            return await self.generators[idx].get_status(task_id)
        except Exception as e:
            logger.error(f"[MultiGenerator] get_status failed: {e}", exc_info=True)
            return {"status": "failed", "error": str(e)}
