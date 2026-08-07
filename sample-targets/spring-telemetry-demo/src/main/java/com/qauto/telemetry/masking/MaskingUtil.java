package com.qauto.telemetry.masking;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class MaskingUtil {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String MASK = "***";

  private MaskingUtil() {}

  public static Result prepare(Object body, int maxBytes) {
    List<String> masked = new ArrayList<>();
    JsonNode node = MAPPER.valueToTree(body == null ? Map.of() : body);
    JsonNode maskedNode = maskNode(node, "", masked);
    try {
      byte[] raw = MAPPER.writeValueAsBytes(maskedNode);
      if (raw.length <= maxBytes) {
        return new Result(MAPPER.convertValue(maskedNode, Object.class), masked, false, null);
      }
      String preview = new String(raw, 0, Math.min(raw.length, maxBytes), StandardCharsets.UTF_8);
      return new Result(
          Map.of("_truncated", true, "preview", preview),
          masked,
          true,
          Map.of(
              "originalBytes", raw.length,
              "keptBytes", preview.getBytes(StandardCharsets.UTF_8).length,
              "maxBytes", maxBytes));
    } catch (Exception ex) {
      return new Result(Map.of("error", "serialize_failed"), masked, false, null);
    }
  }

  private static JsonNode maskNode(JsonNode node, String path, List<String> masked) {
    if (node == null || node.isNull()) {
      return node;
    }
    if (node.isObject()) {
      ObjectNode out = MAPPER.createObjectNode();
      Iterator<Map.Entry<String, JsonNode>> fields = node.fields();
      while (fields.hasNext()) {
        Map.Entry<String, JsonNode> entry = fields.next();
        String key = entry.getKey();
        String child = path.isEmpty() ? key : path + "." + key;
        if (isSensitive(key)) {
          out.put(key, MASK);
          masked.add(child);
        } else {
          out.set(key, maskNode(entry.getValue(), child, masked));
        }
      }
      return out;
    }
    if (node.isArray()) {
      ArrayNode out = MAPPER.createArrayNode();
      int idx = 0;
      for (JsonNode item : node) {
        out.add(maskNode(item, path + "[" + idx + "]", masked));
        idx++;
      }
      return out;
    }
    return node;
  }

  private static boolean isSensitive(String key) {
    String compact = key.toLowerCase(Locale.ROOT).replace("-", "").replace("_", "");
    return compact.contains("password")
        || compact.contains("passwd")
        || compact.contains("secret")
        || compact.contains("token")
        || compact.contains("authorization")
        || compact.contains("cookie")
        || compact.contains("apikey");
  }

  public record Result(Object body, List<String> maskedFields, boolean truncated, Map<String, Object> truncationMeta) {}
}
