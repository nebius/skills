# Nebius Serverless endpoint — create command skeleton (CLI 0.12.265; `ai endpoint create`
# is flags-only, there is no -f/--file spec input). Every valid flag is listed below —
# anything not here is hallucinated; `nebius ai endpoint create --help` is ground truth.
# Workflow: validate with --dry-run first, state the recurring cost (bills create → delete),
# get explicit confirmation, then run once without --dry-run (Tier B gated write).
nebius ai endpoint create \
  --parent-id project-e00example \                # REQUIRED in practice — target project NID (else taken from profile)
  --name my-endpoint \                            # application name
  --image cr.eu-north1.nebius.cloud/e00example/vllm:latest \  # registry/path:tag or registry/path@digest
  --platform gpu-h100-sxm \                       # see nebius-serverless-jobs references; default gpu-h100-sxm (eu-north1)
  --preset 1gpu-16vcpu-200gb \                    # default: minimum preset for the platform
  --container-port 8000/http \                    # repeatable; http → managed https:// URL, tcp → tls://HOST:443, udp → no URL
  --auth token \                                  # none (default — open to the internet) | token; token needs exactly one HTTP port
  --dry-run                                       # validate only; drop for the real (confirmed) run
  # --token-secret <selector>                     # token from MysteryBox (AUTH_TOKEN key) — the right choice for scripts
  # --token <value>                               # caller-supplied token — never leave the literal in scripts or transcripts
  #                                               # with --auth token and neither flag, the platform generates a random token
  #                                               # (readable at .spec.auth_token — extract with jq only, never print raw `get`)
  # --args '<args>'                               # override container arguments
  # --container-command '<cmd>'                   # override container entrypoint
  # --disk-size 250Gi                             # e.g. 100Gi, 500Gi, 1Ti; default 250Gi
  # --env KEY=VALUE                               # repeatable
  # --env-secret KEY=SECRET_SELECTOR              # repeatable; MysteryBox — see nebius-serverless-data-secrets
  # --inject-file local.conf:/etc/app/app.conf    # repeatable; container path absolute, read-only, ≤64 KiB
  # --preemptible                                 # cheaper; platform may stop the VM at any time
  # --public                                      # raw public IP, independent of managed URLs — almost never what you want
  # --registry-secret <selector>                  # MysteryBox secret with REGISTRY_USERNAME/REGISTRY_PASSWORD keys
  # --registry-username <user>                    # plain-text registry auth — prefer --registry-secret
  # --registry-password <pass>                    #   never leave a literal password in scripts or transcripts
  # --shm-size 16Gi                               # /dev/shm; default 16Gi on GPU platforms, 0 on CPU
  # --ssh-key 'ssh-ed25519 AAAA...'               # repeatable; authorizes SSH to the VM
  # --subnet-id vpcsubnet-e00example              # network subnet
  # --volume SOURCE:/container/path[:rw|ro]       # repeatable; also s3://BUCKET:/path[:MODE[:PROFILE]]
  # --working-dir /app                            # absolute path
  # --async                                       # return an operation id; poll `endpoint get` (jq-filtered!) while image pulls
