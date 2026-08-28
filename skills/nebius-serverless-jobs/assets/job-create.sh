# Nebius Serverless job — create command skeleton (CLI 0.12.265; `ai job create` is
# flags-only, there is no -f/--file spec input). Every valid flag is listed below —
# anything not here is hallucinated; `nebius ai job create --help` is ground truth.
# Workflow: validate with --dry-run first, state the cost, get explicit confirmation,
# then run once without --dry-run (Tier B gated write).
nebius ai job create \
  --parent-id project-e00example \                # REQUIRED in practice — target project NID (else taken from profile)
  --name my-job \                                 # application name
  --image cr.eu-north1.nebius.cloud/e00example/train:latest \  # registry/path:tag or registry/path@digest
  --platform gpu-h100-sxm \                       # see references/platform-presets.md; default gpu-h100-sxm (eu-north1)
  --preset 1gpu-16vcpu-200gb \                    # default: minimum preset for the platform
  --dry-run                                       # validate only; drop for the real (confirmed) run
  # --args '<args>'                               # override container arguments
  # --container-command '<cmd>'                   # override container entrypoint
  # --container-port 8080[:80][/http|tcp|udp]     # repeatable; default protocol http
  # --disk-size 250Gi                             # e.g. 100Gi, 500Gi, 1Ti; default 250Gi
  # --env KEY=VALUE                               # repeatable
  # --env-secret KEY=SECRET_SELECTOR              # repeatable; MysteryBox — see nebius-serverless-data-secrets
  # --inject-file local.conf:/etc/app/app.conf    # repeatable; container path absolute, read-only, ≤64 KiB
  # --preemptible                                 # cheaper; platform may stop the VM at any time
  # --registry-secret <selector>                  # MysteryBox secret with REGISTRY_USERNAME/REGISTRY_PASSWORD keys
  # --registry-username <user>                    # plain-text registry auth — prefer --registry-secret
  # --registry-password <pass>                    #   never leave a literal password in scripts or transcripts
  # --restart-policy never|on-failure             # default never
  # --shm-size 16Gi                               # /dev/shm; default 16Gi on GPU platforms, 0 on CPU
  # --ssh-key 'ssh-ed25519 AAAA...'               # repeatable; authorizes SSH to the VM
  # --subnet-id vpcsubnet-e00example              # network subnet
  # --timeout 24h                                 # 1h..168h; default 24h — the job bills until done or timeout
  # --volume SOURCE:/container/path[:rw|ro]       # repeatable; also s3://BUCKET:/path[:MODE[:PROFILE]]
  # --working-dir /app                            # absolute path
  # --async                                       # return an operation id; poll with `ai job get`
