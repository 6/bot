variable "zone_id" {
  description = "Cloudflare zone ID that should route to the Worker"
  type        = string
}

variable "workers_route_pattern" {
  description = "Route pattern for the GitHub webhook Worker"
  type        = string
}

variable "worker_script_name" {
  description = "Cloudflare Worker script name"
  type        = string
  default     = "bot-github-webhook"
}
