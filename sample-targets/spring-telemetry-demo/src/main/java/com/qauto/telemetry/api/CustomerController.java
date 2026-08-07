package com.qauto.telemetry.api;

import com.qauto.telemetry.ingest.TelemetryClient;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {
  private final TelemetryClient client;

  public CustomerController(TelemetryClient client) {
    this.client = client;
  }

  @PostMapping("/search")
  public Map<String, Object> search(@Valid @RequestBody SearchRequest body) {
    emit("validation_passed", null);
    emit("service_called", "CustomerService.search");
    Map<String, Object> response = new HashMap<>();
    response.put("customerId", body.customerId());
    response.put("riskLevel", "HIGH");
    response.put("displayName", "합성고객");
    return response;
  }

  private void emit(String eventName, String service) {
    String runId = MDC.get("testRunId");
    if (runId == null || runId.isBlank()) {
      return;
    }
    Map<String, Object> event = new HashMap<>();
    event.put("timestamp", Instant.now().toString());
    event.put("event", eventName);
    event.put("testRunId", runId);
    event.put("scenarioId", MDC.get("scenarioId"));
    event.put("testCaseId", MDC.get("testCaseId"));
    event.put("inputProfileId", MDC.get("inputProfileId"));
    try {
      event.put("requestSequence", Integer.parseInt(MDC.get("requestSequence")));
    } catch (Exception ignored) {
      event.put("requestSequence", 1);
    }
    if (service != null) {
      event.put("service", service);
    }
    event.put("maskedFields", List.of());
    event.put("source", "spring");
    client.emit(event);
  }

  public record SearchRequest(@NotBlank String customerId, String password) {}
}
