export class ApiError extends Error {
  constructor(message, { status = 0, detail = null, network = false } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.network = network
  }
}
