export type AdapterContext = {
  projectId: string;
  testRunId?: string;
};

export interface EvidenceStorageAdapter {
  save(context: AdapterContext, artifact: Uint8Array): Promise<{ artifactId: string }>;
}

export interface RepositoryAdapter {
  resolveRevision(localPath: string): Promise<{ commitSha: string }>;
}

/** Phase 07 — UI Adapter for custom SI components → native events/locators */
export type LocatorStrategy = "testId" | "role" | "label" | "id" | "name" | "css" | "xpath";

export type UiComponentMapping = {
  name: string;
  mapsTo: "native-input" | "native-button" | string;
  events: string[];
  locatorPreference: LocatorStrategy[];
  valueProp?: string;
  onChangeProp?: string;
};

export type UiBindingMapping = {
  field: string;
  responsePath: string;
  testId: string;
  normalize?: string[];
};

export type UiScreenshotMask = {
  id: string;
  testId: string;
  reason: string;
};

export type UiAdapterConfig = {
  adapterId: string;
  version: string;
  serviceId?: string;
  components: UiComponentMapping[];
  bindings: UiBindingMapping[];
  screenshotMask?: UiScreenshotMask[];
  semanticHints?: Record<string, string>;
};

export function isStableLocatorStrategy(strategy: LocatorStrategy): boolean {
  return strategy !== "css" && strategy !== "xpath";
}
