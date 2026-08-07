package com.qauto.telemetry.ingest;

import com.qauto.telemetry.config.TelemetryProperties;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class TelemetryClient {
  private static final Logger log = LoggerFactory.getLogger(TelemetryClient.class);
  private final TelemetryProperties properties;
  private final RestClient restClient;

  public TelemetryClient(TelemetryProperties properties) {
    this.properties = properties;
    this.restClient = RestClient.create();
  }

  public void emit(Map<String, Object> event) {
    if (!properties.isEnabled()) {
      return;
    }
    try {
      restClient
          .post()
          .uri(properties.getIngestUrl())
          .contentType(MediaType.APPLICATION_JSON)
          .body(Map.of("events", List.of(event)))
          .retrieve()
          .toBodilessEntity();
    } catch (Exception ex) {
      log.warn("telemetry ingest failed: {}", ex.getMessage());
    }
  }
}
