/**
 * OpenRouter client used by all API routes.
 * Uses the openai SDK pointed at OpenRouter's base URL.
 */

import OpenAI from 'openai'

export const openrouter = new OpenAI({
  baseURL: 'https://openrouter.ai/api/v1',
  apiKey: process.env.OPENROUTER_API_KEY ?? '',
})

export const MODEL = 'anthropic/claude-3.5-sonnet'

/**
 * Run a structured JSON extraction prompt.
 * Always returns a parsed object; throws on failure.
 */
export async function extractJSON<T = unknown>(
  systemPrompt: string,
  userContent: string,
): Promise<T> {
  console.log('[v0] extractJSON: sending request to OpenRouter, model:', MODEL)
  console.log('[v0] extractJSON: userContent length:', userContent.length, 'chars')

  let response
  try {
    response = await openrouter.chat.completions.create({
      model: MODEL,
      max_tokens: 4096,
      messages: [
        {
          role: 'system',
          content:
            systemPrompt +
            '\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no code fences, no explanation.',
        },
        { role: 'user', content: userContent },
      ],
    })
  } catch (apiErr: unknown) {
    const msg = apiErr instanceof Error ? apiErr.message : String(apiErr)
    console.error('[v0] extractJSON: OpenRouter API call failed:', msg)
    // Surface the full error object for debugging
    console.error('[v0] extractJSON: full error:', JSON.stringify(apiErr, Object.getOwnPropertyNames(apiErr as object)))
    throw new Error(`OpenRouter API error: ${msg}`)
  }

  const text = response.choices[0]?.message?.content ?? ''
  console.log('[v0] extractJSON: raw response length:', text.length, 'chars, preview:', text.slice(0, 200))

  if (!text) {
    const finishReason = response.choices[0]?.finish_reason
    throw new Error(`Empty response from model (finish_reason: ${finishReason ?? 'unknown'})`)
  }

  // Strip any accidental markdown fences
  const cleaned = text
    .replace(/^```json\s*/i, '')
    .replace(/^```\s*/i, '')
    .replace(/```\s*$/i, '')
    .trim()

  try {
    return JSON.parse(cleaned) as T
  } catch (parseErr) {
    console.error('[v0] extractJSON: JSON parse failed. Raw text:', text.slice(0, 500))
    throw new Error(`JSON parse error: ${parseErr instanceof Error ? parseErr.message : String(parseErr)}. Response started with: ${text.slice(0, 100)}`)
  }
}
