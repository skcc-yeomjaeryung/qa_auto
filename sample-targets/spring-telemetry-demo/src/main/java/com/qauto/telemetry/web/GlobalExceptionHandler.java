package com.qauto.telemetry.web;

import com.qauto.telemetry.ingest.TelemetryClient;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {
  private final TelemetryClient client;

  public GlobalExceptionHandler(TelemetryClient client) {
    this.client = client;
  }

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<Map<String, Object>> validation(MethodArgumentNotValidException ex) {
    emit("validation_failed", ex.getClass().getSimpleName(), ex.getMessage());
    return ResponseEntity.badRequest().body(Map.of("error", "validation_failed"));
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<Map<String, Object>> generic(Exception ex) {
    emit("exception_mapped", ex.getClass().getSimpleName(), ex.getMessage());
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
        .body(Map.of("error", "exception_mapped"));
  }

  private void emit(String event, String errorType, String message) {
    String runId = MDC.get("testRunId");
    if (runId == null || runId.isBlank()) {
      return;
    }
    Map<String, Object> payload = new HashMap<>();
    payload.put("timestamp", Instant.now().toString());
    payload.put("event", event);
    payload.put("testRunId", runId);
    payload.put("scenarioId", MDC.get("scenarioId"));
    payload.put("testCaseId", MDC.get("testCaseId"));
    payload.put("inputProfileId", MDC.get("inputProfileId"));
    try {
      payload.put("requestSequence", Integer.parseInt(MDC.get("requestSequence")));
    } catch (Exception ignored) {
      payload.put("requestSequence", 1);
    }
    payload.put("errorType", errorType);
    payload.put("errorMessage", message == null ? null : message.substring(0, Math.min(message.length(), 200)));
    payload.put("maskedFields", List.of());
    payload.put("source", "spring");
    client.emit(payload);
  }
}
