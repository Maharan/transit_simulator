export function isValidNumber(value: string): boolean {
  if (value.trim() === '') {
    return false
  }
  const parsed = Number(value)
  return Number.isFinite(parsed)
}
