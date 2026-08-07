package com.qauto.telemetry.web;

import com.qauto.telemetry.config.TelemetryProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableConfigurationProperties(TelemetryProperties.class)
public class WebConfig implements WebMvcConfigurer {
  private final TelemetryInterceptor interceptor;

  public WebConfig(TelemetryInterceptor interceptor) {
    this.interceptor = interceptor;
  }

  @Override
  public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(interceptor);
  }

  @Override
  public void addCorsMappings(CorsRegistry registry) {
    registry
        .addMapping("/api/**")
        .allowedOrigins("*")
        .allowedMethods("*")
        .allowedHeaders(
            "Content-Type",
            "Authorization",
            CorrelationFilter.HDR_RUN,
            CorrelationFilter.HDR_SCENARIO,
            CorrelationFilter.HDR_SCENARIO_VER,
            CorrelationFilter.HDR_CASE,
            CorrelationFilter.HDR_PROFILE);
  }
}
