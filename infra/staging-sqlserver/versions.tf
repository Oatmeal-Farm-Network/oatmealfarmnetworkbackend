terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "oatmeal-staging-tfstate"
    prefix = "staging/sqlserver"
  }
}

provider "google" {
  project = var.staging_project_id
  region  = var.region
}
