"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { http } from "@/lib/api";
import { ErrorBox, Loading } from "@/components/ui";
import { QuestionEditor } from "@/components/QuestionEditor";
import type { QuestionDetail } from "@/lib/types";

export default function EditQuestionPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [data, setData] = React.useState<QuestionDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (!id) return;
    http
      .get<QuestionDetail>(`/api/v1/questions/${id}`)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">编辑题目 #{id}</h1>
      <QuestionEditor initial={data} />
    </div>
  );
}
