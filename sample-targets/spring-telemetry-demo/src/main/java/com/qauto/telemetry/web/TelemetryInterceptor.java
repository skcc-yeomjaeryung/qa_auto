package com.qauto.telemetry.web;

import com.qauto.telemetry.ingest.TelemetryClient;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class TelemetryInterceptor implements HandlerInterceptor {
  private final TelemetryClient client;

  public TelemetryInterceptor(TelemetryClient client) {
    this.client = client;
  }

  @Override
  public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
    String runId = MDC.get("testRunId");
    if (runId == null || runId.isBlank()) {
      return true;
    }
    String controller = handler instanceof HandlerMethod hm
        ? hm.getBeanType().getSimpleName() + "." + hm.getMethod().getName()
        : "unknown";
    Map<String, Object> event = new HashMap<>();
    event.put("timestamp", Instant.now().toString());
    event.put("event", "controller_entered");
    event.put("testRunId", runId);
    event.put("scenarioId", emptyToNull(MDC.get("scenarioId")));
    event.put("testCaseId", emptyToNull(MDC.get("testCaseId")));
    event.put("inputProfileId", emptyToNull(MDC.get("inputProfileId")));
    event.put("requestSequence", parseSeq(MDC.get("requestSequence")));
    event.put("controller", controller);
    event.put("httpMethod", request.getMethod());
    event.put("path", request.getRequestURI());
    event.put("maskedFields", List.of());
    event.put("source", "spring");
    client.emit(event);
    return true;
  }

  private static Integer parseSeq(String raw) {
    try {
      return raw == null ? 1 : Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
      return 1;
    }
  }

  private static String emptyToNull(String v) {
    return v == null || v.isBlank() ? null : v;
  }
}
