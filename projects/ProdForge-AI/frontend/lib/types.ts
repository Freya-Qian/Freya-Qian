export type GoalType = "course" | "portfolio" | "real" | "team_review";

export type Project = {
  id: string;
  name: string;
  idea: string;
  goal_type: GoalType;
  default_competitor_id: string | null;
  current_stage: StageKey;
  status: string;
  created_at: string;
  updated_at: string;
};

export type StageKey = "clarify" | "competitor" | "position" | "prd" | "tasks" | "package" | string;

export type SampleIdea = {
  name: string;
  idea: string;
};

export type SamplesResponse = {
  samples: SampleIdea[];
  goal_types: Record<GoalType, string>;
};

export type ModelSettings = {
  configured: boolean;
  model_api_key: string;
  model_name: string;
  model_base_url: string;
};

export type Question = {
  id: string;
  round_num: number;
  dimension: string;
  question: string;
  hint: string;
  answer: string;
  skipped: boolean;
  required: boolean;
};

export type Brief = {
  id: string;
  project_id: string;
  version: number;
  status: string;
  one_liner: string;
  target_users: string;
  scenarios: string;
  pains: string;
  goals: string;
  non_goals: string;
  success_metrics: string;
  external_systems: string;
  knowledge_sources: string;
  open_questions: string;
  created_at: string;
  updated_at: string;
};

export type Competitor = {
  id: string;
  name: string;
  url: string;
  positioning: string;
  target_users: string;
  key_features: string;
  strengths: string;
  gaps: string;
  is_default: boolean;
};

export type Evidence = {
  id: string;
  competitor_id: string;
  ref_key: string;
  source_type: string;
  source_url: string;
  evidence_type: string;
  raw_excerpt: string;
  structured_claim: string;
  implication: string;
  confidence: string;
  used_in: string;
  fetched_at: string;
};

export type Positioning = {
  id: string;
  project_id: string;
  one_liner: string;
  target_users: string;
  value_proposition: string;
  differentiators: Array<{ point?: string; evidence_refs?: string[] }>;
  non_goals: string;
  comparison: Array<Record<string, unknown>>;
  evidence_refs: string[];
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
};

export type Prd = {
  id: string;
  project_id: string;
  version: number;
  status: string;
  sections: Array<{ title: string; content: string; evidence_refs?: string[]; status?: string }>;
  evidence_refs: string[];
  created_at: string;
  updated_at: string;
};

export type DevTask = {
  id: string;
  module: string;
  title: string;
  description: string;
  priority: "P0" | "P1" | "P2" | string;
  acceptance_criteria: string;
  dependencies: string[];
  source_refs: string[];
  export_status: string;
};

export type DecisionLog = {
  id: string;
  project_id: string | null;
  decision: string;
  reason: string;
  source: string;
  evidence_refs: string;
  created_at: string;
};

export type Feedback = {
  id: string;
  project_id: string;
  content: string;
  affected_sections: string;
  author_type: string;
  created_at: string;
};

export type TaskOut = {
  id: string;
  project_id: string | null;
  task_type: string;
  status: "queued" | "processing" | "success" | "failed" | string;
  error: string;
  result_json: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
};
