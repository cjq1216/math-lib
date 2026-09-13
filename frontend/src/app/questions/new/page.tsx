import { QuestionEditor } from "@/components/QuestionEditor";

export default function NewQuestionPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">录入题目</h1>
      <QuestionEditor initial={null} />
    </div>
  );
}
