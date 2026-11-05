const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function money(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function sf(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Math.round(value).toLocaleString('en-US')
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(digits)}%`
}

// Dates arrive as YYYY-MM-DD. Read the parts directly so a time zone can't shift the month.
export function monthYear(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [y, m] = iso.split('-').map(Number)
  if (!y || !m) return iso
  return `${MONTHS[m - 1]} ${y}`
}

export function fullDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return iso
  return `${MONTHS[m - 1]} ${d}, ${y}`
}

export function term(months: number | null | undefined): string {
  if (months === null || months === undefined) return 'Unknown'
  if (months < 0) return 'Expired'
  return `${months} mo`
}

export function timestamp(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}
