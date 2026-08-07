package com.qauto.telemetry.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.qauto.telemetry.config.TelemetryProperties;
import com.qauto.telemetry.ingest.TelemetryClient;
import com.qauto.telemetry.masking.MaskingUtil;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;
import org.springframework.web.util.ContentCachingResponseWrapper;

@Component
public class CorrelationFilter extends OncePerRequestFilter {
  public static final String HDR_RUN = "X-Test-Run-ID";
  public static final String HDR_SCENARIO = "X-Scenario-ID";
  public static final String HDR_CASE = "X-Test-Case-ID";
  public static final String HDR_PROFILE = "X-Input-Profile-ID";
  public static final String HDR_SCENARIO_VER = "X-Scenario-Version";

  private final TelemetryClient client;
  private final TelemetryProperties properties;
  private final ObjectMapper mapper = new ObjectMapper();
  private final AtomicInteger sequence = new AtomicInteger(0);

  public CorrelationFilter(TelemetryClient client, TelemetryProperties properties) {
    this.client = client;
    this.properties = properties;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
      throws ServletException, IOException {
    if (request.getRequestURI().startsWith("/actuator")) {
      filterChain.doFilter(request, response);
      return;
    }
    ContentCachingRequestWrapper req = new ContentCachingRequestWrapper(request);
    ContentCachingResponseWrapper res = new ContentCachingResponseWrapper(response);
    String runId = header(req, HDR_RUN);
    String scenarioId = header(req, HDR_SCENARIO);
    String caseId = header(req, HDR_CASE);
    String profileId = header(req, HDR_PROFILE);
    int seq = sequence.incrementAndGet();
    long started = System.currentTimeMillis();
    try {
      MDC.put("testRunId", runId == null ? "" : runId);
      MDC.put("scenarioId", scenarioId == null ? "" : scenarioId);
      MDC.put("testCaseId", caseId == null ? "" : caseId);
      MDC.put("inputProfileId", profileId == null ? "" : profileId);
      MDC.put("requestSequence", String.valueOf(seq));
      req.setAttribute("qauto.requestSequence", seq);

      if (runId != null && !runId.isBlank()) {
        client.emit(
            baseEvent(
                "request_received",
                runId,
                scenarioId,
                caseId,
                profileId,
                seq,
                req,
                null,
                null,
                null,
                List.of()));
      }

      filterChain.doFilter(req, res);

      if (runId != null && !runId.isBlank()) {
        Object reqBody = readJson(req.getContentAsByteArray());
        Object resBody = readJson(res.getContentAsByteArray());
        MaskingUtil.Result reqPrep = MaskingUtil.prepare(reqBody, properties.getMaxBodyBytes());
        MaskingUtil.Result resPrep = MaskingUtil.prepare(resBody, properties.getMaxBodyBytes());
        List<String> masked = new ArrayList<>();
        masked.addAll(reqPrep.maskedFields());
        masked.addAll(resPrep.maskedFields());
        client.emit(
            baseEvent(
                "response_returned",
                runId,
                scenarioId,
                caseId,
                profileId,
                seq,
                req,
                reqPrep.body(),
                resPrep.body(),
                res.getStatus(),
                masked,
                System.currentTimeMillis() - started,
                reqPrep.truncated() || resPrep.truncated(),
                Map.of("request", reqPrep.truncationMeta(), "response", resPrep.truncationMeta())));
      }
    } finally {
      res.copyBodyToResponse();
      MDC.clear();
    }
  }

  private Map<String, Object> baseEvent(
      String event,
      String runId,
      String scenarioId,
      String caseId,
      String profileId,
      int seq,
      HttpServletRequest req,
      Object requestBody,
      Object responseBody,
      Integer status,
      List<String> masked) {
    return baseEvent(
        event, runId, scenarioId, caseId, profileId, seq, req, requestBody, responseBody, status, masked, null, false, null);
  }

  private Map<String, Object> baseEvent(
      String event,
      String runId,
      String scenarioId,
      String caseId,
      String profileId,
      int seq,
      HttpServletRequest req,
      Object requestBody,
      Object responseBody,
      Integer status,
      List<String> masked,
      Long durationMs,
      boolean truncated,
      Map<String, Object> truncationMeta) {
    Map<String, Object> m = new HashMap<>();
    m.put("timestamp", Instant.now().toString());
    m.put("event", event);
    m.put("testRunId", runId);
    m.put("scenarioId", scenarioId);
    m.put("scenarioVersion", header(req, HDR_SCENARIO_VER));
    m.put("testCaseId", caseId);
    m.put("inputProfileId", profileId);
    m.put("requestSequence", seq);
    m.put("httpMethod", req.getMethod());
    m.put("path", req.getRequestURI());
    m.put("request", requestBody);
    m.put("response", responseBody);
    m.put("status", status);
    m.put("durationMs", durationMs);
    m.put("maskedFields", masked == null ? List.of() : masked);
    m.put("truncated", truncated);
    m.put("truncationMeta", truncationMeta);
    m.put("source", "spring");
    return m;
  }

  private Object readJson(byte[] bytes) {
    if (bytes == null || bytes.length == 0) {
      return Map.of();
    }
    try {
      return mapper.readValue(bytes, Object.class);
    } catch (Exception ex) {
      return Map.of("raw", new String(bytes).substring(0, Math.min(bytes.length, 200)));
    }
  }

  private static String header(HttpServletRequest req, String name) {
    String v = req.getHeader(name);
    return v == null || v.isBlank() ? null : v.trim();
  }
}
