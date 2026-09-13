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
  created_at?: string;
}

export interface QuestionDetail extends Question {
  sub_questions?: SubQuestion[];
  answers?: QuestionAnswer[];
  knowledge_points?: { kp_id: number; is_primary: boolean }[];
}

export interface SubQuestion {
  id: number;
  label: string;
  stem?: string | null;
  score: number;
  answer?: string | null;
}

export interface QuestionAnswer {
  id: number;
  blank_index: number;
  answer_text: string;
  is_primary: boolean;
}

export interface KnowledgePoint {
  id: number;
  code?: string | null;
  name: string;
  parent_id?: number | null;
  grade?: number | null;
  semester?: string | null;
  chapter?: string | null;
  difficulty_hint?: number | null;
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

export interface HomeworkResultItem {
  id: number;
  student_id: number;
  total_score?: number | null;
  max_score?: number | null;
  percentage?: number | null;
  time_spent_minutes?: number | null;
}

export interface WeakPoint {
  kp_id: number;
  kp_name?: string | null;
  kp_code?: string | null;
  accuracy: number;
  severity: string;
  attempts: number;
  recommended_practice_count?: number | null;
}

export interface StudentOverview {
  student_id: number;
  name: string;
  average_score?: number | null;
  total_homework?: number | null;
  knowledge_points_practiced?: number | null;
  weak_points?: { kp_id: number; accuracy: number; severity: string }[];
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
