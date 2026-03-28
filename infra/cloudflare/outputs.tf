output "worker_route_id" {
  description = "Cloudflare route ID for the GitHub webhook Worker"
  value       = cloudflare_workers_route.github_webhook.id
}
