/**
 * LaTeX → OMML (Office Math Markup Language) 转换器
 *
 * Pipeline: LaTeX → MathML (temml) → 清理 → OMML (mathml2omml) → PPTX后处理
 *
 * 提取自 OpenMAIC (THU-MAIC/OpenMAIC) lib/export/latex-to-omml.ts
 * 依赖: temml, mathml2omml
 */

import temml from 'temml';

// mathml2omml 使用动态导入以支持可选依赖
let _mml2omml: ((mathml: string) => string) | null = null;

async function getMml2omml(): Promise<(mathml: string) => string> {
  if (_mml2omml) return _mml2omml;
  try {
    const mod = await import('mathml2omml');
    _mml2omml = (mod as any).mml2omml || (mod as any).default || mod;
    return _mml2omml!;
  } catch {
    throw new Error('mathml2omml is not installed. Run: npm install mathml2omml');
  }
}

/**
 * 移除 mathml2omml 不支持的 MathML 元素
 */
function stripUnsupportedMathML(mathml: string): string {
  const unsupported = ['mpadded', 'menclose'];
  let result = mathml;
  for (const tag of unsupported) {
    result = result.replace(new RegExp(`<${tag}[^>]*>`, 'g'), '');
    result = result.replace(new RegExp(`</${tag}>`, 'g'), '');
  }
  return result;
}

/**
 * 构建 <a:rPr> 数学运行属性 — PowerPoint 要求 Cambria Math 字体
 */
function buildMathRPr(szHundredths?: number): string {
  const szAttr = szHundredths ? ` sz="${szHundredths}"` : '';
  return (
    `<a:rPr lang="en-US" i="1"${szAttr}>` +
    '<a:latin typeface="Cambria Math" panose="02040503050406030204" charset="0"/>' +
    '<a:cs typeface="Cambria Math" panose="02040503050406030204" charset="0"/>' +
    '</a:rPr>'
  );
}

/**
 * PPTX OMML 后处理:
 * 1. 去掉 DOCX 专用的 xmlns:w
 * 2. 去掉冗余的 xmlns:m
 * 3. 注入 Cambria Math 字体属性
 */
function postProcessOmml(omml: string, szHundredths?: number): string {
  let result = omml;
  const rpr = buildMathRPr(szHundredths);

  result = result.replace(/ xmlns:w="[^"]*"/g, '');
  result = result.replace(/ xmlns:m="[^"]*"/g, '');

  // 在 <m:r> 内的 <m:t> 前注入 <a:rPr>
  result = result.replace(/<m:r>(\s*)<m:t/g, `<m:r>$1${rpr}$1<m:t`);

  // 填充空的 <m:ctrlPr/>
  result = result.replace(/<m:ctrlPr\/>/g, `<m:ctrlPr>${rpr}</m:ctrlPr>`);
  result = result.replace(/<m:ctrlPr><\/m:ctrlPr>/g, `<m:ctrlPr>${rpr}</m:ctrlPr>`);

  return result;
}

/**
 * 将 LaTeX 字符串转为 OMML XML
 *
 * @param latex LaTeX 表达式 (不含定界符)
 * @param fontSize 可选字体大小(pt)
 * @returns OMML XML 字符串，失败返回 null
 */
export async function latexToOmml(latex: string, fontSize?: number): Promise<string | null> {
  try {
    const mathml = temml.renderToString(latex, { throwOnError: false });
    const cleaned = stripUnsupportedMathML(mathml);
    const mml2omml = await getMml2omml();
    const omml = String(mml2omml(cleaned));
    const szHundredths = fontSize ? Math.round(fontSize * 100) : undefined;
    return postProcessOmml(omml, szHundredths);
  } catch (err) {
    console.warn(`[latex-to-omml] Failed to convert: "${latex}":`, err);
    return null;
  }
}

/**
 * 同步版本 — 仅使用 temml 渲染为 HTML (不生成 OMML)
 * 适用于 Remotion 预览等不需要 PPTX 的场景
 */
export function latexToHtml(latex: string, displayMode: boolean = true): string | null {
  try {
    return temml.renderToString(latex, { throwOnError: false, displayMode });
  } catch {
    return null;
  }
}
