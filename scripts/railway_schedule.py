import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request


API_URL = os.environ.get("RAILWAY_GRAPHQL_URL", "https://backboard.railway.app/graphql/v2")


def require_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} wajib diisi.")
    return value


def clean_secret_value(name):
    value = require_env(name)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    for line in lines:
        prefix = line.split(":", 1)[0].strip().upper() if ":" in line else ""
        if prefix in {"SECRET", "VALUE"}:
            return line.split(":", 1)[1].strip()
    for line in lines:
        prefix = line.split(":", 1)[0].strip().upper() if ":" in line else ""
        if prefix == name.upper():
            return line.split(":", 1)[1].strip()
    if len(lines) > 1:
        return lines[-1]
    return value


def clean_uuid_secret(name):
    value = clean_secret_value(name)
    match = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        value,
    )
    if not match:
        raise RuntimeError(f"{name} harus berupa UUID Railway.")
    return match.group(0)


def get_railway_token():
    value = clean_secret_value("RAILWAY_TOKEN")
    if ":" in value and value.split(":", 1)[0].strip().upper() == "RAILWAY_TOKEN":
        value = value.split(":", 1)[1].strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    token = "".join(value.split())
    if not token:
        raise RuntimeError("RAILWAY_TOKEN kosong setelah dibersihkan.")
    return token


def build_auth_headers(token, auth_mode):
    if auth_mode == "project":
        return {"Project-Access-Token": token}
    return {"Authorization": f"Bearer {token}"}


def execute_graphql_request(query, variables, token, auth_mode):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            **build_auth_headers(token, auth_mode),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://railway.com",
            "Referer": "https://railway.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Railway API HTTP {exc.code}: {detail}") from exc

    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=False))

    return payload.get("data") or {}


def graphql_request(query, variables):
    token = get_railway_token()
    try:
        return execute_graphql_request(query, variables, token, "bearer")
    except RuntimeError as exc:
        error_text = str(exc).lower()
        if "not authorized" not in error_text and "unauthorized" not in error_text:
            raise
        print("Bearer auth failed, retrying as Railway project token.", file=sys.stderr)
        return execute_graphql_request(query, variables, token, "project")


def get_latest_deployment(service_id, environment_id):
    query = """
    query getLatestDeployment($serviceId: String!, $environmentId: String!) {
      serviceInstance(environmentId: $environmentId, serviceId: $serviceId) {
        latestDeployment {
          id
          status
        }
      }
    }
    """
    data = graphql_request(
        query,
        {
            "serviceId": service_id,
            "environmentId": environment_id,
        },
    )
    deployment = (data.get("serviceInstance") or {}).get("latestDeployment")
    if not deployment or not deployment.get("id"):
        raise RuntimeError("Latest deployment Railway tidak ditemukan.")
    return deployment


def stop_deployment(deployment_id):
    mutation = """
    mutation stopDeployment($id: String!) {
      deploymentStop(id: $id)
    }
    """
    graphql_request(mutation, {"id": deployment_id})


def restart_deployment(deployment_id):
    mutation = """
    mutation restartDeployment($id: String!) {
      deploymentRestart(id: $id)
    }
    """
    graphql_request(mutation, {"id": deployment_id})


def redeploy_service(service_id, environment_id):
    mutation = """
    mutation redeployService($serviceId: String!, $environmentId: String!) {
      serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    graphql_request(
        mutation,
        {
            "serviceId": service_id,
            "environmentId": environment_id,
        },
    )


def main(argv):
    parser = argparse.ArgumentParser(description="Stop atau start Railway deployment terjadwal.")
    parser.add_argument("--action", choices=["stop", "start"], required=True)
    args = parser.parse_args(argv)

    service_id = clean_uuid_secret("RAILWAY_SERVICE_ID")
    environment_id = clean_uuid_secret("RAILWAY_ENVIRONMENT_ID")
    deployment = get_latest_deployment(service_id, environment_id)
    deployment_id = deployment["id"]
    print(f"Latest deployment: {deployment_id} ({deployment.get('status')})")

    if args.action == "stop":
        stop_deployment(deployment_id)
        print("Railway deployment stopped.")
        return 0

    try:
        restart_deployment(deployment_id)
        print("Railway deployment restarted.")
    except RuntimeError as exc:
        print(f"Restart failed, trying redeploy instead: {exc}", file=sys.stderr)
        redeploy_service(service_id, environment_id)
        print("Railway service redeployed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
