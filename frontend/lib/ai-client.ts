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
  const response = await openrouter.chat.completions.create({
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

  const text = response.choices[0]?.message?.content ?? ''

  // Strip any accidental markdown fences
  const cleaned = text.replace(/^```json\s*/i, '').replace(/^```\s*/i, '').replace(/```\s*$/i, '').trim()

  return JSON.parse(cleaned) as T
}
