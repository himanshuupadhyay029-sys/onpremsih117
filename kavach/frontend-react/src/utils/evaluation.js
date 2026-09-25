// View-state helpers for the backend RAG evaluation object. Scores are always computed
// by the backend; this module only merges streamed events and formats values.

export const EVALUATION_METRICS = [
  { key: 'faithfulness', label: 'Faithfulness', hint: 'Answer claims supported by the retrieved context' },
  { key: 'answer_relevancy', label: 'Answer Relevancy', hint: 'How directly the answer addresses the question' },
  { key: 'context_precision', label: 'Context Precision', hint: 'Ranked passages relevant to the reference answer' },
  { key: 'context_recall', label: 'Context Recall', hint: 'Reference-answer facts present in the retrieved context' },
];

const METRIC_KEYS = EVALUATION_METRICS.map((m) => m.key);

export function shouldShowEvaluation(evaluation) {
  return Boolean(
    evaluation && evaluation.enabled && evaluation.status !== 'disabled' && evaluation.status !== 'not_applicable'
  );
}

export function metricView(evaluation, key) {
  const status = evaluation?.metric_status?.[key] || (evaluation?.status === 'running' ? 'running' : 'failed');
  const score = evaluation?.metrics?.[key];
  const error = evaluation?.errors?.[key] || null;

  if (status === 'completed' && typeof score === 'number') {
    const tone = score >= 0.8 ? 'good' : score >= 0.5 ? 'fair' : 'poor';
    return { state: 'completed', display: score.toFixed(2), score, tone, error: null };
  }
  if (status === 'running') return { state: 'running', display: '…', score: null, tone: 'neutral', error: null };
  if (status === 'not_applicable') return { state: 'not_applicable', display: 'N/A', score: null, tone: 'neutral', error };
  return { state: 'failed', display: 'Failed', score: null, tone: 'neutral', error: error || 'Metric unavailable' };
}

export function applyEvaluationEvent(evaluation, eventName, payload) {
  if (eventName === 'evaluation_done') return payload;
  if (!evaluation) return evaluation;

  if (eventName === 'evaluation_stage') {
    return { ...evaluation, stage: { name: payload.stage, status: payload.status } };
  }

  if (eventName === 'evaluation_metric' && METRIC_KEYS.includes(payload.metric)) {
    return {
      ...evaluation,
      metrics: { ...evaluation.metrics, [payload.metric]: payload.score ?? null },
      metric_status: { ...evaluation.metric_status, [payload.metric]: payload.status },
      errors: { ...evaluation.errors, [payload.metric]: payload.error ?? null },
    };
  }

  if (eventName === 'connection_lost' && evaluation.status === 'running') {
    const metricStatus = { ...evaluation.metric_status };
    const errors = { ...evaluation.errors };
    for (const key of METRIC_KEYS) {
      if (metricStatus[key] === 'running') {
        metricStatus[key] = 'failed';
        errors[key] = 'Evaluation stream interrupted';
      }
    }
    return { ...evaluation, status: 'failed', metric_status: metricStatus, errors };
  }

  return evaluation;
}
