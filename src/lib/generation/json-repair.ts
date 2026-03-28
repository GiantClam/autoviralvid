/**
 * JSON修复器 — 从LLM响应中提取JSON，4级回退策略
 *
 * 提取自 OpenMAIC (THU-MAIC/OpenMAIC) lib/generation/json-repair.ts
 * 策略: code block → 括号匹配 → jsonrepair库 → 控制字符清理
 */

import { jsonrepair } from 'jsonrepair';

export interface ParseResult<T> {
  success: boolean;
  data?: T;
  error?: string;
}

/**
 * 从LLM响应中提取JSON — 4级回退策略
 *
 * @param response LLM原始响应文本
 * @returns 解析后的数据或null
 */
export function parseJsonResponse<T>(response: string): T | null {
  if (!response || !response.trim()) return null;

  // Strategy 1: 提取 markdown code block 中的JSON
  const codeBlockRegex = /```(?:json)?\s*([\s\S]*?)```/g;
  let match;
  while ((match = codeBlockRegex.exec(response)) !== null) {
    const extracted = match[1].trim();
    if (extracted.startsWith('{') || extracted.startsWith('[')) {
      const result = tryParseJson<T>(extracted);
      if (result !== null) return result;
    }
  }

  // Strategy 2: 直接查找JSON结构 (括号匹配)
  const jsonStartArray = response.indexOf('[');
  const jsonStartObject = response.indexOf('{');

  if (jsonStartArray !== -1 || jsonStartObject !== -1) {
    const startIndex =
      jsonStartArray === -1
        ? jsonStartObject
        : jsonStartObject === -1
          ? jsonStartArray
          : Math.min(jsonStartArray, jsonStartObject);

    // 找到匹配的闭括号 (感知字符串内括号)
    let depth = 0;
    let endIndex = -1;
    let inString = false;
    let escapeNext = false;

    for (let i = startIndex; i < response.length; i++) {
      const char = response[i];

      if (escapeNext) {
        escapeNext = false;
        continue;
      }
      if (char === '\\' && inString) {
        escapeNext = true;
        continue;
      }
      if (char === '"' && !escapeNext) {
        inString = !inString;
        continue;
      }
      if (!inString) {
        if (char === '[' || char === '{') depth++;
        else if (char === ']' || char === '}') {
          depth--;
          if (depth === 0) {
            endIndex = i;
            break;
          }
        }
      }
    }

    if (endIndex !== -1) {
      const jsonStr = response.substring(startIndex, endIndex + 1);
      const result = tryParseJson<T>(jsonStr);
      if (result !== null) return result;
    }
  }

  // Strategy 3: 整个响应作为JSON
  const result = tryParseJson<T>(response.trim());
  if (result !== null) return result;

  // Strategy 4: 失败
  return null;
}

/**
 * 尝试解析JSON，带多种修复手段
 */
function tryParseJson<T>(jsonStr: string): T | null {
  // Attempt 1: 直接解析
  try {
    return JSON.parse(jsonStr) as T;
  } catch {
    // 继续修复
  }

  // Attempt 2: 修复常见JSON问题
  try {
    let fixed = jsonStr;

    // 修复LaTeX转义 (如 \frac, \left, \right)
    fixed = fixed.replace(/"([^"]*?)"/g, (_match, content) => {
      const fixedContent = content.replace(/\\([a-zA-Z])/g, '\\\\$1');
      return `"${fixedContent}"`;
    });

    // 修复无效转义序列
    fixed = fixed.replace(/\\([^"\\\/bfnrtu\n\r])/g, (match, char) => {
      if (/[a-zA-Z]/.test(char)) return '\\\\' + char;
      return match;
    });

    // 修复截断的JSON数组/对象
    const trimmed = fixed.trim();
    if (trimmed.startsWith('[') && !trimmed.endsWith(']')) {
      const lastCompleteObj = fixed.lastIndexOf('}');
      if (lastCompleteObj > 0) {
        fixed = fixed.substring(0, lastCompleteObj + 1) + ']';
      }
    } else if (trimmed.startsWith('{') && !trimmed.endsWith('}')) {
      const openBraces = (fixed.match(/{/g) || []).length;
      const closeBraces = (fixed.match(/}/g) || []).length;
      if (openBraces > closeBraces) {
        fixed += '}'.repeat(openBraces - closeBraces);
      }
    }

    return JSON.parse(fixed) as T;
  } catch {
    // 继续
  }

  // Attempt 3: 使用 jsonrepair 库
  try {
    const repaired = jsonrepair(jsonStr);
    return JSON.parse(repaired) as T;
  } catch {
    // 继续
  }

  // Attempt 4: 清理控制字符
  try {
    let fixed = jsonStr;
    fixed = fixed.replace(/[\x00-\x1F\x7F]/g, (char) => {
      switch (char) {
        case '\n': return '\\n';
        case '\r': return '\\r';
        case '\t': return '\\t';
        default: return '';
      }
    });
    return JSON.parse(fixed) as T;
  } catch {
    return null;
  }
}
