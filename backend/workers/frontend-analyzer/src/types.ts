export type Evidence = {
  file: string;
  line: number;
  extractor: string;
  confidence: number;
};

export type Screen = {
  id: string;
  name: string;
  route: string;
  framework: "next-app" | "next-pages" | "react-router" | "unknown";
  componentIds: string[];
  evidence: Evidence;
};

export type ComponentNode = {
  id: string;
  name: string;
  kind: string;
  props: string[];
  children: string[];
  evidence: Evidence;
};

export type InputField = {
  id: string;
  name: string | null;
  kind: string;
  testId: string | null;
  label: string | null;
  role: string | null;
  required: boolean;
  constraints: Record<string, unknown>;
  componentId: string | null;
  evidence: Evidence;
};

export type EventBinding = {
  id: string;
  event: string;
  handlerName: string | null;
  handlerResolved: boolean;
  componentId: string | null;
  evidence: Evidence;
};

export type ValidationRule = {
  id: string;
  field: string | null;
  kind: string;
  expression: string;
  required: boolean;
  evidence: Evidence;
};

export type ApiCall = {
  id: string;
  method: string;
  path: string;
  normalizedPath: string;
  requestShape: string | null;
  responseType: string | null;
  client: "fetch" | "axios" | "react-query" | "unknown";
  evidence: Evidence;
};

export type RouteTransition = {
  id: string;
  fromHint: string | null;
  to: string;
  kind: string;
  evidence: Evidence;
};

export type Binding = {
  id: string;
  from: string;
  to: string;
  relation: string;
  evidence: Evidence;
};

export type ExistingTest = {
  id: string;
  framework: string;
  file: string;
  steps: Array<{ action: string; target?: string; value?: string }>;
  evidence: Evidence;
};

export type Unresolved = {
  id: string;
  kind: string;
  symbol: string;
  reason: string;
  evidence: Evidence;
};

export type FileHashEntry = {
  path: string;
  sha256: string;
};

export type FrontendAnalysisResult = {
  schemaVersion: "frontend-analysis/v1";
  commitSha: string | null;
  workspacePath: string;
  analyzedAt: string;
  screens: Screen[];
  components: ComponentNode[];
  inputs: InputField[];
  events: EventBinding[];
  validations: ValidationRule[];
  apiCalls: ApiCall[];
  routeTransitions: RouteTransition[];
  bindings: Binding[];
  existingTests: ExistingTest[];
  unresolved: Unresolved[];
  fileHashes: FileHashEntry[];
};
