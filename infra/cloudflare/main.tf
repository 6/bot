terraform {
  required_version = ">= 1.9.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 5.0.0"
    }
  }
}

resource "cloudflare_workers_route" "github_webhook" {
  zone_id = var.zone_id
  pattern = var.workers_route_pattern
  script  = var.worker_script_name
}
