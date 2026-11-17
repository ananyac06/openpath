# OpenPath Security Architecture & Responsible Access Policy
**Version 1.0 | Local-First Security & Network Boundaries**

---

## 1. Local-First Design & Data Sovereignty

OpenPath is designed from first principles to be 100% local-first:
- **Zero Cloud Dependencies:** No mandatory cloud databases, third-party authentication services, or telemetry beacons.
- **Configurable Standard Directories (XDG Base Directory Specification):**
  - **Configuration:** `~/.config/openpath/config.toml` (override with `OPENPATH_CONFIG_DIR`)
  - **Data & SQLite DB:** `~/.local/share/openpath/openpath.db` (override with `OPENPATH_DATA_DIR` or `OPENPATH_DB_PATH`)
  - **State & Logs:** `~/.local/state/openpath/` (override with `OPENPATH_STATE_DIR`)
- **Secrets Management:** External API keys (e.g. Reddit client secret, GitHub token) are loaded strictly via environment variables or the local config file. They are never logged, never committed to git, and never included in error traces.

---

## 2. Server-Side Request Forgery (SSRF) Prevention

Because OpenPath crawls web pages and follows links discovered in job descriptions and ATS feeds, it enforces strict network boundary validation before every request and after every HTTP redirect:

### Network Security Rules
1. **Scheme Validation:** Only `http://` and `https://` schemes are permitted. Schemes such as `file://`, `ftp://`, `gopher://`, `data:`, or `javascript:` are rejected immediately.
2. **IP & Hostname Blacklisting:**
   Before dispatching any HTTP request, the target hostname is resolved via DNS. If the resolved IP address falls into any of the following ranges, the request is aborted with an `SSRFSecurityViolation`:
   - IPv4 Loopback: `127.0.0.0/8`
   - RFC 1918 Private Ranges:
     - `10.0.0.0/8`
     - `172.16.0.0/12`
     - `192.168.0.0/16`
   - Link-Local & Cloud Metadata:
     - `169.254.0.0/16` (including AWS/GCP/Azure metadata endpoint `169.254.169.254`)
   - IPv6 Loopback & Private:
     - `::1/128`, `fc00::/7`, `fe80::/10`
   - Broadcast / Reserved: `0.0.0.0/8`, `240.0.0.0/4`, `255.255.255.255/32`
3. **Redirect Validation:** All redirects are intercepted and re-evaluated through the same SSRF validator. OpenPath never follows a redirect that targets a private, internal, or loopback IP.

---

## 3. Content Handling & Execution Boundaries

1. **No Code Execution:** Downloaded files are parsed as passive data structures (HTML, XML, JSON, text). No downloaded scripts, JavaScript runtimes, or executable binaries are ever executed.
2. **Path Traversal Protection:** Snapshot filenames and cache paths are derived via cryptographic SHA-256 hashes of the canonical URL, preventing any directory traversal attacks (e.g. `../../etc/passwd`).
3. **Payload & Memory Caps:**
   - Maximum HTTP response body size: 10 MB.
   - Streamed reading with early abort if `Content-Length` or cumulative bytes exceed the cap.
   - Prevents decompression bombs and memory exhaustion.

---

## 4. Responsible Access & Rate Limiting

OpenPath respects remote infrastructure:
- **Per-Domain Request Budgets:** Token-bucket throttlers limit outbound requests per domain (default: 1 request per second for general domains; 2 requests per second for authorized public ATS APIs).
- **Robots.txt Adherence:** Automatically fetches and caches `robots.txt` before crawling custom web domains.
- **Adaptive Backoff & Jitter:** On encountering HTTP 429 (Too Many Requests) or HTTP 503 (Service Unavailable):
  - Honors the `Retry-After` header if present.
  - Applies exponential backoff with randomized jitter ($t = \text{base} \times 2^{\text{attempt}} + \text{rand}(0, 1)$).
  - Pauses the offending source in the frontier after 3 consecutive failures.
- **Prohibited Techniques:**
  - No rotating residential/commercial proxies to bypass blocks.
  - No CAPTCHA solvers or bypass mechanisms.
  - No automated credential stuffing or unauthorized authenticated scraping.
  - If a source requires authentication or blocks access, it is flagged truthfully as `credential_required` or `policy_blocked` in the ledger.
