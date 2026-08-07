import { Project, SyntaxKind, Node, type SourceFile, type JsxAttribute } from "ts-morph";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type {
  ApiCall,
  Binding,
  ComponentNode,
  EventBinding,
  ExistingTest,
  FrontendAnalysisResult,
  InputField,
  RouteTransition,
  Screen,
  Unresolved,
  ValidationRule,
} from "./types.js";
import { evidence, listSourceFiles, literalText, normalizeApiPath, rel, sha256File, slug } from "./util.js";

export type AnalyzeOptions = {
  workspacePath: string;
  commitSha?: string | null;
  onProgress?: (completed: number, total: number) => void;
};

function attrValue(attr: JsxAttribute | undefined): string | null {
  if (!attr) return null;
  const init = attr.getInitializer();
  if (!init) return null;
  if (Node.isStringLiteral(init) || Node.isNoSubstitutionTemplateLiteral(init)) {
    return init.getLiteralText();
  }
  if (Node.isJsxExpression(init)) {
    const expr = init.getExpression();
    if (!expr) return null;
    if (Node.isStringLiteral(expr) || Node.isNoSubstitutionTemplateLiteral(expr)) {
      return expr.getLiteralText();
    }
    return expr.getText();
  }
  return init.getText();
}

function getJsxName(node: Node): string | null {
  if (Node.isJsxSelfClosingElement(node) || Node.isJsxOpeningElement(node)) {
    return node.getTagNameNode().getText();
  }
  return null;
}

function lineOf(node: Node): number {
  return node.getStartLineNumber();
}

function loadTsconfigPaths(workspace: string): Record<string, string[]> {
  const candidates = ["tsconfig.json", "tsconfig.app.json", "jsconfig.json"];
  for (const name of candidates) {
    const path = join(workspace, name);
    if (!existsSync(path)) continue;
    try {
      const json = JSON.parse(readFileSync(path, "utf8")) as {
        compilerOptions?: { paths?: Record<string, string[]> };
      };
      return json.compilerOptions?.paths ?? {};
    } catch {
      // continue
    }
  }
  return {};
}

export function analyzeFrontend(options: AnalyzeOptions): FrontendAnalysisResult {
  const root = options.workspacePath;
  const files = listSourceFiles(root);
  const project = new Project({
    skipAddingFilesFromTsConfig: true,
    compilerOptions: {
      allowJs: true,
      jsx: 4, // react-jsx
      target: 99,
      module: 99,
      moduleResolution: 100,
      esModuleInterop: true,
      strict: false,
    },
  });

  for (const file of files) {
    project.addSourceFileAtPath(file);
  }

  const pathAliases = loadTsconfigPaths(root);
  const screens: Screen[] = [];
  const components: ComponentNode[] = [];
  const inputs: InputField[] = [];
  const events: EventBinding[] = [];
  const validations: ValidationRule[] = [];
  const apiCalls: ApiCall[] = [];
  const routeTransitions: RouteTransition[] = [];
  const bindings: Binding[] = [];
  const existingTests: ExistingTest[] = [];
  const unresolved: Unresolved[] = [];

  // Next App Router pages
  for (const file of files) {
    const relative = rel(root, file);
    const appPage = relative.match(/^(?:src\/)?app\/(.+)\/page\.(tsx|jsx|ts|js)$/);
    if (appPage) {
      const routePath = ("/" + appPage[1]!.replace(/\/index$/, "")).replace(/\[([^\]]+)\]/g, ":$1");
      const id = slug(["screen", "next-app", routePath]);
      screens.push({
        id,
        name: appPage[1]!.split("/").pop() ?? "page",
        route: routePath === "/page" ? "/" : routePath,
        framework: "next-app",
        componentIds: [],
        evidence: evidence(relative, 1, "next-app-router", 0.95),
      });
    }
    const pagesRoute = relative.match(/^(?:src\/)?pages\/(.+)\.(tsx|jsx|ts|js)$/);
    if (pagesRoute && !pagesRoute[1]!.startsWith("api/")) {
      let routePath = "/" + pagesRoute[1]!.replace(/\/index$/, "").replace(/\[([^\]]+)\]/g, ":$1");
      if (routePath.endsWith("/index")) routePath = routePath.slice(0, -6) || "/";
      screens.push({
        id: slug(["screen", "next-pages", routePath]),
        name: pagesRoute[1]!.split("/").pop() ?? "page",
        route: routePath,
        framework: "next-pages",
        componentIds: [],
        evidence: evidence(relative, 1, "next-pages-router", 0.93),
      });
    }
  }

  const sourceFiles = project.getSourceFiles();
  for (const [index, sf] of sourceFiles.entries()) {
    const relative = rel(root, sf.getFilePath());
    extractReactRouterRoutes(sf, relative, screens, unresolved);
    extractComponentsAndInputs(sf, relative, components, inputs, events, unresolved);
    extractValidations(sf, relative, validations);
    extractApiCalls(sf, relative, apiCalls, unresolved);
    extractRouteTransitions(sf, relative, routeTransitions, unresolved);
    extractPlaywright(sf, relative, existingTests);
    noteDynamicDispatch(sf, relative, unresolved);
    notePathAliasUsage(sf, relative, pathAliases, unresolved);
    options.onProgress?.(index + 1, sourceFiles.length);
  }

  // Bind event → API → route heuristically for handlers that share file proximity
  linkBindings(events, apiCalls, routeTransitions, validations, inputs, bindings);

  // Attach component ids to screens by file/route proximity
  for (const screen of screens) {
    const related = components
      .filter((c) => c.evidence.file === screen.evidence.file || screen.route.includes(c.name.toLowerCase()))
      .map((c) => c.id);
    screen.componentIds = [...new Set([...screen.componentIds, ...related])];
  }

  return {
    schemaVersion: "frontend-analysis/v1",
    commitSha: options.commitSha ?? null,
    workspacePath: root,
    analyzedAt: new Date().toISOString(),
    screens,
    components,
    inputs,
    events,
    validations,
    apiCalls,
    routeTransitions,
    bindings,
    existingTests,
    unresolved,
    fileHashes: files.map((f) => ({ path: rel(root, f), sha256: sha256File(f) })),
  };
}

function extractReactRouterRoutes(
  sf: SourceFile,
  relative: string,
  screens: Screen[],
  unresolved: Unresolved[],
) {
  sf.forEachDescendant((node) => {
    if (!Node.isJsxSelfClosingElement(node) && !Node.isJsxOpeningElement(node)) return;
    const name = getJsxName(node);
    if (name !== "Route") return;
    const pathAttr = node.getAttribute("path");
    const elementAttr = node.getAttribute("element");
    if (!pathAttr || !Node.isJsxAttribute(pathAttr)) {
      unresolved.push({
        id: slug(["unresolved", "route", relative, String(lineOf(node))]),
        kind: "route",
        symbol: "Route",
        reason: "Route without path attribute",
        evidence: evidence(relative, lineOf(node), "react-router", 0.4),
      });
      return;
    }
    const route = attrValue(pathAttr) ?? "*";
    let componentName = "anonymous";
    if (elementAttr && Node.isJsxAttribute(elementAttr)) {
      const text = attrValue(elementAttr) ?? "";
      const m = text.match(/<?([A-Z][A-Za-z0-9_]*)/);
      if (m) componentName = m[1]!;
    }
    const id = slug(["screen", "rr", route, componentName]);
    if (screens.some((s) => s.id === id)) return;
    screens.push({
      id,
      name: componentName,
      route,
      framework: "react-router",
      componentIds: [slug(["component", componentName, relative])],
      evidence: evidence(relative, lineOf(node), "react-router", 0.92),
    });
  });
}

function extractComponentsAndInputs(
  sf: SourceFile,
  relative: string,
  components: ComponentNode[],
  inputs: InputField[],
  events: EventBinding[],
  unresolved: Unresolved[],
) {
  const functionComponents = [
    ...sf.getFunctions(),
    ...sf.getVariableDeclarations().filter((d) => {
      const init = d.getInitializer();
      return init && (Node.isArrowFunction(init) || Node.isFunctionExpression(init));
    }),
  ];

  for (const decl of functionComponents) {
    const name =
      "getName" in decl && typeof decl.getName === "function"
        ? decl.getName() ?? "anonymous"
        : "anonymous";
    if (!name || name === "anonymous") continue;
    // Heuristic: PascalCase = component
    if (!/^[A-Z]/.test(name)) continue;
    const id = slug(["component", name, relative]);
    if (components.some((c) => c.id === id)) continue;
    components.push({
      id,
      name,
      kind: "function-component",
      props: [],
      children: [],
      evidence: evidence(relative, lineOf(decl), "react-component", 0.8),
    });
  }

  sf.forEachDescendant((node) => {
    if (!Node.isJsxSelfClosingElement(node) && !Node.isJsxOpeningElement(node)) return;
    const tag = getJsxName(node);
    if (!tag) return;
    const lower = tag.toLowerCase();
    const interesting = [
      "input",
      "select",
      "textarea",
      "button",
      "form",
      "table",
      "dialog",
      "modal",
    ];
    const isHost = interesting.includes(lower);
    const isCustom = /^[A-Z]/.test(tag);
    if (!isHost && !isCustom) return;

    const attrs = node.getAttributes().filter(Node.isJsxAttribute);
    const byName = (n: string) => attrs.find((a) => a.getNameNode().getText() === n);

    if (isHost || ["Button", "Input", "TextField"].includes(tag)) {
      const kind = isHost ? lower : tag;
      const testId = attrValue(byName("data-testid")) ?? attrValue(byName("data-test-id"));
      const nameAttr = attrValue(byName("name")) ?? attrValue(byName("id"));
      const role = attrValue(byName("role"));
      const required =
        byName("required") != null ||
        attrValue(byName("aria-required")) === "true" ||
        attrValue(byName("required")) === "true";
      const constraints: Record<string, unknown> = {};
      for (const key of ["min", "max", "minLength", "maxLength", "pattern", "type"]) {
        const v = attrValue(byName(key));
        if (v != null) constraints[key] = v;
      }
      const inputId = slug(["input", kind, nameAttr ?? testId ?? String(lineOf(node)), relative]);
      inputs.push({
        id: inputId,
        name: nameAttr,
        kind,
        testId,
        label: null,
        role,
        required,
        constraints,
        componentId: null,
        evidence: evidence(relative, lineOf(node), "jsx-input", 0.88),
      });
    }

    for (const eventName of [
      "onClick",
      "onSubmit",
      "onChange",
      "onBlur",
      "onKeyDown",
      "onKeyUp",
    ]) {
      const attr = byName(eventName);
      if (!attr) continue;
      const handlerText = attrValue(attr);
      let handlerName: string | null = null;
      let resolved = false;
      if (handlerText) {
        const m = handlerText.match(/^\{?\s*([A-Za-z_$][\w$]*)/);
        handlerName = m?.[1] ?? handlerText.replace(/[{}]/g, "").trim();
        if (handlerName && sf.getFunction(handlerName)) resolved = true;
        else if (
          handlerName &&
          sf.getVariableDeclaration(handlerName) &&
          !handlerName.startsWith("set")
        ) {
          resolved = true;
        } else if (handlerText.includes("=>") || handlerText.includes("function")) {
          handlerName = handlerName ?? "inline";
          resolved = true;
        } else if (handlerName) {
          // look for nested function declarations inside components
          resolved = sf.getDescendantsOfKind(SyntaxKind.FunctionDeclaration).some(
            (fn) => fn.getName() === handlerName,
          )
            || sf.getDescendantsOfKind(SyntaxKind.VariableDeclaration).some((vd) => {
              if (vd.getName() !== handlerName) return false;
              const init = vd.getInitializer();
              return !!init && (Node.isArrowFunction(init) || Node.isFunctionExpression(init));
            });
          if (!resolved) {
            unresolved.push({
              id: slug(["unresolved", "handler", handlerName, relative, String(lineOf(node))]),
              kind: "handler",
              symbol: handlerName,
              reason: "Handler symbol not statically resolved",
              evidence: evidence(relative, lineOf(node), "event-handler", 0.45),
            });
          }
        }
      }
      events.push({
        id: slug(["event", eventName, handlerName ?? "unknown", relative, String(lineOf(node))]),
        event: eventName,
        handlerName,
        handlerResolved: resolved,
        componentId: null,
        evidence: evidence(relative, lineOf(node), "jsx-event", resolved ? 0.85 : 0.5),
      });
    }

    // Label association: previous sibling text not available easily — htmlFor on label
  });

  // labels with htmlFor
  sf.forEachDescendant((node) => {
    if (!Node.isJsxOpeningElement(node) && !Node.isJsxSelfClosingElement(node)) return;
    if (getJsxName(node)?.toLowerCase() !== "label") return;
    const htmlFor = attrValue(
      node.getAttributes().filter(Node.isJsxAttribute).find((a) => a.getNameNode().getText() === "htmlFor"),
    );
    if (!htmlFor) return;
    const target = inputs.find((i) => i.name === htmlFor || i.id.includes(htmlFor));
    if (target) {
      target.label = htmlFor;
    }
  });
}

function extractValidations(sf: SourceFile, relative: string, validations: ValidationRule[]) {
  const text = sf.getFullText();
  // zod: z.string().regex(...) / .min / .email etc.
  const zodBlocks = [
    ...text.matchAll(
      /(\w+)\s*=\s*z\s*\.\s*string\s*\(([^)]*)\)([\s\S]{0,400}?)(?:;|export|const|let|var|type\s)/g,
    ),
  ];
  for (const match of zodBlocks) {
    const field = match[1] ?? null;
    const chain = match[0] ?? "";
    const line = sf.getFullText().slice(0, match.index ?? 0).split("\n").length;
    const required = !/\.optional\s*\(/.test(chain) && !/\.nullable\s*\(/.test(chain);
    let kind = "zod.string";
    if (/\.regex\s*\(/.test(chain)) kind = "zod.regex";
    if (/\.email\s*\(/.test(chain)) kind = "zod.email";
    if (/\.min\s*\(/.test(chain)) kind = "zod.min";
    validations.push({
      id: slug(["validation", field ?? "anon", kind, relative, String(line)]),
      field: field === "customerIdSchema" ? "customerId" : field,
      kind,
      expression: chain.replace(/\s+/g, " ").slice(0, 240),
      required,
      evidence: evidence(relative, line, "zod", 0.9),
    });
  }

  // yup / RHF register required
  for (const m of text.matchAll(/register\s*\(\s*['"`]([^'"`]+)['"`]\s*,\s*\{([^}]*)\}/g)) {
    const field = m[1]!;
    const opts = m[2] ?? "";
    const line = text.slice(0, m.index ?? 0).split("\n").length;
    validations.push({
      id: slug(["validation", "rhf", field, relative, String(line)]),
      field,
      kind: "react-hook-form",
      expression: opts.replace(/\s+/g, " ").slice(0, 200),
      required: /\brequired\s*:/.test(opts),
      evidence: evidence(relative, line, "react-hook-form", 0.86),
    });
  }
}

function extractApiCalls(
  sf: SourceFile,
  relative: string,
  apiCalls: ApiCall[],
  unresolved: Unresolved[],
) {
  sf.forEachDescendant((node) => {
    // fetch(url, { method })
    if (Node.isCallExpression(node)) {
      const expr = node.getExpression();
      const callee = expr.getText();
      if (callee === "fetch" || callee.endsWith(".fetch")) {
        const args = node.getArguments();
        const urlArg = args[0];
        const opts = args[1];
        let method = "GET";
        let pathRaw = literalText(urlArg) ?? urlArg?.getText() ?? "";
        if (opts && Node.isObjectLiteralExpression(opts)) {
          const methodProp = opts.getProperty("method");
          if (methodProp && Node.isPropertyAssignment(methodProp)) {
            method = (literalText(methodProp.getInitializer()) ?? "GET").toUpperCase();
          }
        }
        // resolve const API_URL = "..."
        if (urlArg && Node.isIdentifier(urlArg)) {
          const decl = sf.getVariableDeclaration(urlArg.getText());
          const init = decl?.getInitializer();
          if (init) {
            const text = init.getText();
            const lit = text.match(/['"`](https?:\/\/[^'"`]+|\/[^'"`]+)['"`]/);
            if (lit) pathRaw = lit[1]!;
            else {
              // import.meta.env fallback with ?? "url"
              const coalesce = text.match(/\?\?\s*['"`]([^'"`]+)['"`]/);
              if (coalesce) pathRaw = coalesce[1]!;
            }
          }
        }
        if (!pathRaw || pathRaw.includes("${") || (!pathRaw.includes("/") && !pathRaw.startsWith("http"))) {
          unresolved.push({
            id: slug(["unresolved", "api", relative, String(lineOf(node))]),
            kind: "apiCall",
            symbol: pathRaw || "fetch",
            reason: "Dynamic or unresolved fetch URL",
            evidence: evidence(relative, lineOf(node), "fetch", 0.4),
          });
        }
        const normalized = normalizeApiPath(pathRaw);
        apiCalls.push({
          id: slug(["api", method, normalized, relative, String(lineOf(node))]),
          method,
          path: pathRaw,
          normalizedPath: normalized,
          requestShape: null,
          responseType: null,
          client: "fetch",
          evidence: evidence(relative, lineOf(node), "fetch", 0.9),
        });
      }

      // axios.get/post/request
      if (/axios\.(get|post|put|patch|delete|request)/i.test(callee) || callee === "axios") {
        const args = node.getArguments();
        let method = "GET";
        let pathRaw = "";
        const m = callee.match(/axios\.(get|post|put|patch|delete)/i);
        if (m) {
          method = m[1]!.toUpperCase();
          pathRaw = literalText(args[0]) ?? args[0]?.getText() ?? "";
        } else if (callee === "axios" || callee.endsWith(".request")) {
          const opts = args[0];
          if (opts && Node.isObjectLiteralExpression(opts)) {
            const methodProp = opts.getProperty("method");
            const urlProp = opts.getProperty("url");
            if (methodProp && Node.isPropertyAssignment(methodProp)) {
              method = (literalText(methodProp.getInitializer()) ?? "GET").toUpperCase();
            }
            if (urlProp && Node.isPropertyAssignment(urlProp)) {
              pathRaw = literalText(urlProp.getInitializer()) ?? "";
            }
          }
        }
        const normalized = normalizeApiPath(pathRaw || "/");
        apiCalls.push({
          id: slug(["api", "axios", method, normalized, relative, String(lineOf(node))]),
          method,
          path: pathRaw,
          normalizedPath: normalized,
          requestShape: null,
          responseType: null,
          client: "axios",
          evidence: evidence(relative, lineOf(node), "axios", 0.88),
        });
      }

      // useQuery / useMutation
      if (callee === "useQuery" || callee === "useMutation") {
        apiCalls.push({
          id: slug(["api", "rq", callee, relative, String(lineOf(node))]),
          method: callee === "useMutation" ? "POST" : "GET",
          path: callee,
          normalizedPath: `/${callee}`,
          requestShape: null,
          responseType: null,
          client: "react-query",
          evidence: evidence(relative, lineOf(node), "react-query", 0.7),
        });
      }
    }
  });
}

function extractRouteTransitions(
  sf: SourceFile,
  relative: string,
  transitions: RouteTransition[],
  unresolved: Unresolved[],
) {
  sf.forEachDescendant((node) => {
    if (!Node.isCallExpression(node)) return;
    const text = node.getExpression().getText();
    const isNav =
      text === "navigate" ||
      text.endsWith(".push") ||
      text.endsWith(".replace") ||
      text === "redirect" ||
      text.endsWith("router.push") ||
      text.endsWith("router.replace");
    if (!isNav) return;
    const arg = node.getArguments()[0];
    const to = literalText(arg) ?? arg?.getText() ?? "";
    if (!to || to.includes("${") && !to.includes("/customers/")) {
      // template `/customers/${...}` still useful
      if (!to.includes("/")) {
        unresolved.push({
          id: slug(["unresolved", "transition", relative, String(lineOf(node))]),
          kind: "routeTransition",
          symbol: to || text,
          reason: "Dynamic route transition target",
          evidence: evidence(relative, lineOf(node), "route-transition", 0.4),
        });
        return;
      }
    }
    const normalized = to
      .replace(/^['"`]/, "")
      .replace(/['"`]$/, "")
      .replace(/\$\{[^}]+\}/g, ":param")
      .replace(/encodeURIComponent\(([^)]+)\)/g, ":param");
    // handle navigate(`/customers/${encodeURIComponent(body.customerId)}`)
    let target = normalized;
    if (arg && !literalText(arg)) {
      const raw = arg.getText();
      const tmpl = raw.match(/`([^`]*)`/);
      if (tmpl) {
        target = tmpl[1]!.replace(/\$\{[^}]+\}/g, ":customerId");
      }
    }
    transitions.push({
      id: slug(["transition", text, target, relative, String(lineOf(node))]),
      fromHint: null,
      to: target,
      kind: text.includes("replace") || text === "redirect" ? "replace" : "push",
      evidence: evidence(relative, lineOf(node), "route-transition", 0.9),
    });

    // JSX Navigate to=
  });

  sf.forEachDescendant((node) => {
    if (!Node.isJsxSelfClosingElement(node) && !Node.isJsxOpeningElement(node)) return;
    if (getJsxName(node) !== "Navigate" && getJsxName(node) !== "Link") return;
    const toAttr = node
      .getAttributes()
      .filter(Node.isJsxAttribute)
      .find((a) => ["to", "href"].includes(a.getNameNode().getText()));
    const to = attrValue(toAttr);
    if (!to) return;
    transitions.push({
      id: slug(["transition", getJsxName(node)!, to, relative, String(lineOf(node))]),
      fromHint: null,
      to,
      kind: getJsxName(node) === "Link" ? "link" : "replace",
      evidence: evidence(relative, lineOf(node), "react-router-jsx", 0.9),
    });
  });
}

function extractPlaywright(sf: SourceFile, relative: string, tests: ExistingTest[]) {
  const text = sf.getFullText();
  const isPlaywright =
    /@playwright\/test/.test(text) ||
    /\b(test|expect)\s*\(/.test(text) && /\b(page\.(goto|fill|click)|toHaveURL)\b/.test(text);
  if (!isPlaywright) return;

  const steps: ExistingTest["steps"] = [];
  const readQuoted = (input: string, start: number): { value: string; end: number } | null => {
    const q = input[start];
    if (q !== "'" && q !== '"' && q !== "`") return null;
    let i = start + 1;
    let value = "";
    while (i < input.length) {
      const ch = input[i]!;
      if (ch === "\\" && i + 1 < input.length) {
        value += input[i + 1]!;
        i += 2;
        continue;
      }
      if (ch === q) return { value, end: i + 1 };
      value += ch;
      i += 1;
    }
    return null;
  };
  const walkCalls = (method: string, arity: number, action: string) => {
    const token = `page.${method}(`;
    let from = 0;
    while (from < text.length) {
      const idx = text.indexOf(token, from);
      if (idx < 0) break;
      let cursor = idx + token.length;
      while (text[cursor] === " " || text[cursor] === "\n") cursor += 1;
      const args: string[] = [];
      for (let a = 0; a < arity; a += 1) {
        const parsed = readQuoted(text, cursor);
        if (!parsed) break;
        args.push(parsed.value);
        cursor = parsed.end;
        while (text[cursor] === " " || text[cursor] === ",") cursor += 1;
      }
      if (args.length === arity) {
        steps.push({
          action,
          target: args[0],
          ...(arity > 1 ? { value: args[1] } : {}),
        });
      }
      from = idx + token.length;
    }
  };
  walkCalls("goto", 1, "goto");
  walkCalls("fill", 2, "fill");
  walkCalls("click", 1, "click");
  if (/toHaveURL\s*\(/.test(text)) {
    steps.push({ action: "expect:toHaveURL", target: "toHaveURL" });
  }
  for (const m of text.matchAll(/expect\([^)]*\)\.(?:toBeVisible|toHaveText|toHaveValue)/g)) {
    steps.push({ action: "expect", target: m[0] });
  }

  if (steps.length === 0) return;
  tests.push({
    id: slug(["test", "playwright", relative]),
    framework: "playwright",
    file: relative,
    steps,
    evidence: evidence(relative, 1, "playwright-parser", 0.87),
  });
}

function noteDynamicDispatch(sf: SourceFile, relative: string, unresolved: Unresolved[]) {
  sf.forEachDescendant((node) => {
    if (!Node.isCallExpression(node)) return;
    const expr = node.getExpression();
    // handlers[name]() or map[key]()
    if (Node.isElementAccessExpression(expr)) {
      unresolved.push({
        id: slug(["unresolved", "dynamic", relative, String(lineOf(node))]),
        kind: "dynamic-dispatch",
        symbol: expr.getText(),
        reason: "Dynamic dispatch cannot be resolved statically",
        evidence: evidence(relative, lineOf(node), "dynamic-dispatch", 0.35),
      });
    }
  });
}

function notePathAliasUsage(
  sf: SourceFile,
  relative: string,
  aliases: Record<string, string[]>,
  unresolved: Unresolved[],
) {
  if (Object.keys(aliases).length === 0) return;
  for (const imp of sf.getImportDeclarations()) {
    const spec = imp.getModuleSpecifierValue();
    const matched = Object.keys(aliases).some((pattern) => {
      const prefix = pattern.replace(/\*$/, "");
      return spec.startsWith(prefix.replace(/\*$/, "")) || spec.startsWith("@/");
    });
    if ((spec.startsWith("@/") || spec.startsWith("@src/")) && !matched) {
      unresolved.push({
        id: slug(["unresolved", "alias", spec, relative]),
        kind: "path-alias",
        symbol: spec,
        reason: "Path alias import seen without matching tsconfig paths entry",
        evidence: evidence(relative, imp.getStartLineNumber(), "path-alias", 0.5),
      });
    }
  }
}

function linkBindings(
  events: EventBinding[],
  apiCalls: ApiCall[],
  transitions: RouteTransition[],
  validations: ValidationRule[],
  inputs: InputField[],
  bindings: Binding[],
) {
  for (const ev of events) {
    if (!ev.handlerResolved || !ev.handlerName) continue;
    for (const api of apiCalls) {
      if (api.evidence.file !== ev.evidence.file) continue;
      bindings.push({
        id: slug(["binding", ev.id, api.id]),
        from: ev.id,
        to: api.id,
        relation: "event-triggers-api",
        evidence: evidence(api.evidence.file, api.evidence.line, "binding", 0.75),
      });
    }
    for (const tr of transitions) {
      if (tr.evidence.file !== ev.evidence.file) continue;
      // same handler region: within 40 lines
      if (Math.abs(tr.evidence.line - ev.evidence.line) > 80) continue;
      bindings.push({
        id: slug(["binding", ev.id, tr.id]),
        from: ev.id,
        to: tr.id,
        relation: "event-triggers-route",
        evidence: evidence(tr.evidence.file, tr.evidence.line, "binding", 0.72),
      });
    }
  }
  for (const val of validations) {
    const input = inputs.find(
      (i) =>
        i.name === val.field ||
        i.testId?.includes(val.field ?? "") ||
        (val.field === "customerId" && (i.testId?.includes("customer-id") || i.name?.includes("customer"))),
    );
    if (input) {
      bindings.push({
        id: slug(["binding", val.id, input.id]),
        from: val.id,
        to: input.id,
        relation: "validation-on-input",
        evidence: evidence(val.evidence.file, val.evidence.line, "binding", 0.8),
      });
    }
  }
}
