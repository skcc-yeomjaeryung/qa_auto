# spring-telemetry-demo (Phase 10)

Sample Spring Boot Backend that:

1. Reads correlation headers (`X-Test-Run-ID`, `X-Scenario-ID`, `X-Test-Case-ID`, `X-Input-Profile-ID`)
2. Puts them into MDC (cleared after request)
3. Emits structured events to Control Plane `POST /api/test-telemetry/backend`
4. Masks password/token/cookie fields and truncates large payloads

## Run

```bash
export JAVA_HOME="$(/usr/libexec/java_home 2>/dev/null || echo /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home)"
cd sample-targets/spring-telemetry-demo
mvn -q spring-boot:run
```

Default port: `8088`  
Ingest URL: `http://127.0.0.1:8000/api/test-telemetry/backend`

## Smoke

```bash
curl -s -X POST http://127.0.0.1:8088/api/customers/search \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Run-ID: RUN-demo' \
  -H 'X-Scenario-ID: SCN-demo' \
  -H 'X-Test-Case-ID: TC-demo' \
  -H 'X-Input-Profile-ID: IP-demo' \
  -d '{"customerId":"C10001","password":"secret"}'
```

Then:

```bash
curl -s http://127.0.0.1:8000/api/runs/RUN-demo/backend-events | jq .
```
