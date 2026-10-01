/**
 * 前端共享类型定义（与后端 Pydantic 响应契约对齐）
 */

export type UserRole = "admin" | "teacher";

export interface CurrentUser {
  id: number;
  username: string;
  real_name: string;
  email?: string | null;
  phone?: string | null;
  role: UserRole;
  is_active: boolean;
  avatar_url?: string | null;
  subject?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: CurrentUser;
}

export interface UserCreatePayload {
  username: string;
  password: string;
  real_name: string;
  email?: string | null;
  phone?: string | null;
  role: UserRole;
  subject?: string | null;
  notes?: string | null;
}

export interface UserUpdatePayload {
  real_name?: string;
  email?: string | null;
  phone?: string | null;
  role?: UserRole;
  is_active?: boolean;
  subject?: string | null;
  notes?: string | null;
  password?: string;
}

export interface ClassUpdatePayload {
  name?: string;
  grade?: number;
  semester?: string;
  head_teacher_id?: number | null;
  notes?: string | null;
  is_active?: boolean;
}

export interface ClassCreatePayload {
  name: string;
  grade: number;
  semester: string;
  head_teacher_id?: number | null;
  teacher_ids?: number[];
  notes?: string | null;
}

export interface ClassTeacher {
  id: number;
  username: string;
  real_name: string;
}

export interface StudentUpdatePayload {
  name?: string;
  gender?: string | null;
  grade?: number;
  enrollment_year?: number | null;
  phone?: string | null;
  parent_phone?: string | null;
  notes?: string | null;
  is_active?: boolean;
}

export interface StudentCreatePayload {
  student_no: string;
  name: string;
  gender?: string | null;
  grade: number;
  enrollment_year?: number | null;
  phone?: string | null;
  parent_phone?: string | null;
  notes?: string | null;
  class_id?: number | null;
}

export interface Student {
  id: number;
  student_no: string;
  name: string;
  gender?: string | null;
  grade: number;
  enrollment_year?: number | null;
  phone?: string | null;
  parent_phone?: string | null;
  average_score?: number | null;
  notes?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ImportSummary {
  created: number;
  updated: number;
  errors: ImportErrorItem[];
}

export interface ImportErrorItem {
  row?: number | null;
  column?: string | null;
  code: string;
  message: string;
}

export type QuestionType =
  | "choice_single"
  | "choice_multi"
  | "fill"
  | "judge"
  | "solution"
  | "proof";

export const QUESTION_TYPE_LABEL: Record<QuestionType, string> = {
  choice_single: "单选题",
  choice_multi: "多选题",
  fill: "填空题",
  judge: "判断题",
  solution: "解答题",
  proof: "证明题",
};

export const DIFFICULTY_LABEL: Record<number, string> = {
  1: "1 极易",
  2: "2 较易",
  3: "3 中等",
  4: "4 较难",
  5: "5 很难",
};

export interface QuestionMatchRule {
  rule_type?: "exact" | "allow_set" | "numeric" | "fraction" | "regex" | "unordered_set";
  allow_set?: string[];
  tolerance?: number;
  pattern?: string;
  case_sensitive?: boolean;
  delimiter?: string;
}

export interface QuestionMediaItem {
  id?: number;
  media_id: number;
  usage_type: "stem" | "option" | "analysis" | "attachment";
  display_order?: number;
  alt_text?: string | null;
  caption?: string | null;
  access_url?: string | null;
  original_name?: string | null;
}

export interface MediaResourceItem {
  id: number;
  uuid: string;
  original_name: string;
  url?: string | null;
  width?: number | null;
  height?: number | null;
  file_size: number;
  mime_type?: string | null;
  reference_count: number;
}

export interface Question {
  id: number;
  stem: string;
  question_type: QuestionType;
  difficulty: number;
  total_score: number;
  options?: string[] | null;
  answer?: string | null;
  analysis?: string | null;
  tags?: string[] | null;
  is_verified?: boolean;
  checksum?: string | null;
  created_at?: string;
}

export interface QuestionDetail extends Question {
  sub_questions?: SubQuestion[];
  answers?: QuestionAnswer[];
  knowledge_points?: { kp_id: number; is_primary: boolean; weight?: number }[];
  media_items?: QuestionMediaItem[];
}

export interface SubQuestion {
  id?: number;
  label: string;
  stem?: string | null;
  score: number;
  answer?: string | null;
  analysis?: string | null;
  display_order?: number;
}

export interface QuestionAnswer {
  id?: number;
  blank_index: number;
  answer_text: string;
  is_primary: boolean;
  match_rule?: QuestionMatchRule | null;
}

export interface KnowledgePoint {
  id: number;
  code?: string | null;
  name: string;
  parent_id?: number | null;
  parent_code?: string | null;
  grade?: number | null;
  semester?: string | null;
  chapter?: string | null;
  section?: string | null;
  difficulty_hint?: number | null;
  subject?: string;
  description?: string | null;
  display_order?: number;
  is_active?: boolean;
  children?: KnowledgePoint[];
}

export interface PaperSummary {
  id: number;
  title: string;
  total_score: number;
  duration_minutes: number;
  status: string;
  question_count?: number | null;
  created_at?: string;
}

export interface PaperQuestionItem {
  id: number;
  display_order: number;
  section?: string | null;
  score: number;
  stem: string;
  answer?: string | null;
  analysis?: string | null;
  options?: unknown;
}

export interface PaperDetail {
  id: number;
  title: string;
  description?: string | null;
  total_score: number;
  duration_minutes: number;
  status: string;
  questions: PaperQuestionItem[];
}

export interface PaperConstraint {
  total_score: number;
  duration_minutes: number;
  type_distribution: Record<string, number>;
  difficulty_ratio: Record<string, number>;
  required_kps: number[];
  forbidden_kps: number[];
}

export interface ClassItem {
  id: number;
  name: string;
  grade: number;
  semester: string;
  head_teacher_id?: number | null;
  notes?: string | null;
  is_active: boolean;
}

export interface StudentItem {
  student_id: number;
  student_no?: string | null;
  name: string;
  gender?: string | null;
  phone?: string | null;
}

export interface HomeworkItem {
  id: number;
  title: string;
  type: string;
  status: string;
  paper_id: number;
  due_at?: string | null;
  created_at?: string;
}

export interface HomeworkQuestionResultItem {
  id: number;
  paper_question_id: number;
  question_id: number;
  score: number;
  max_score: number;
  is_correct: boolean;
  answer_text?: string | null;
  time_spent_seconds?: number | null;
}

export interface HomeworkStudentItem {
  student_id: number;
  student_no?: string | null;
  name: string;
  class_id?: number | null;
  class_name?: string | null;
}

export interface HomeworkPaperQuestionItem {
  id: number;
  question_id: number;
  display_order: number;
  score: number;
  stem_snapshot?: string | null;
}

export interface HomeworkResultItem {
  id: number;
  student_id: number;
  total_score?: number | null;
  max_score?: number | null;
  percentage?: number | null;
  time_spent_minutes?: number | null;
  question_results?: HomeworkQuestionResultItem[];
}

export interface HomeworkDetail {
  id: number;
  title: string;
  type: string;
  status: string;
  paper_id: number;
  class_ids?: number[] | null;
  student_ids?: number[] | null;
  due_at?: string | null;
  results: HomeworkResultItem[];
  target_students: HomeworkStudentItem[];
  paper_questions: HomeworkPaperQuestionItem[];
}

export interface WeakPoint {
  kp_id: number;
  kp_name?: string | null;
  kp_code?: string | null;
  accuracy: number;
  severity: string;
  attempts: number;
  recommended_practice_count?: number | null;
  trend?: string | null;
  recent_5_accuracy?: number | null;
  is_resolved?: boolean;
  resolved_at?: string | null;
}

export interface StudentOverview {
  student_id: number;
  name: string;
  average_score?: number | null;
  total_homework?: number | null;
  knowledge_points_practiced?: number | null;
  weak_points?: {
    kp_id: number;
    accuracy: number;
    severity: string;
    trend?: string | null;
    recent_5_accuracy?: number | null;
  }[];
}

export interface ClassOverview {
  class_id: number;
  student_count: number;
  total_homework: number;
  avg_score?: number | null;
  max_score?: number | null;
  min_score?: number | null;
}

export interface RankRow {
  rank: number;
  student_id: number;
  name: string;
  student_no?: string | null;
  total_score?: number | null;
  max_score?: number | null;
  percentage?: number | null;
}

export interface LlmTaskStatus {
  task_id: number;
  task_type: string;
  status: "pending" | "running" | "success" | "failed";
  progress: number;
  progress_message?: string | null;
  result?: unknown;
  error_message?: string | null;
}
