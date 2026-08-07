package com.qauto.telemetry.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "qauto.telemetry")
public class TelemetryProperties {
  private String ingestUrl = "http://127.0.0.1:8000/api/test-telemetry/backend";
  private boolean enabled = true;
  private int maxBodyBytes = 8192;

  public String getIngestUrl() {
    return ingestUrl;
  }

  public void setIngestUrl(String ingestUrl) {
    this.ingestUrl = ingestUrl;
  }

  public boolean isEnabled() {
    return enabled;
  }

  public void setEnabled(boolean enabled) {
    this.enabled = enabled;
  }

  public int getMaxBodyBytes() {
    return maxBodyBytes;
  }

  public void setMaxBodyBytes(int maxBodyBytes) {
    this.maxBodyBytes = maxBodyBytes;
  }
}
