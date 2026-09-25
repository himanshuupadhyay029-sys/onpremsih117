import test from 'node:test';
import assert from 'node:assert/strict';
import { EVALUATION_METRICS, applyEvaluationEvent, metricView, shouldShowEvaluation } from './evaluation.js';

const running = {
  enabled: true,
  status: 'running',
  metrics: { faithfulness: null, answer_relevancy: null, context_precision: null, context_recall: null },
  metric_status: {
    faithfulness: 'running',
    answer_relevancy: 'running',
    context_precision: 'running',
    context_recall: 'running',
  },
  errors: {
    ground_truth: null,
    faithfulness: null,
    answer_relevancy: null,
    context_precision: null,
    context_recall: null,
  },
};

test('renders exactly the four metrics', () => {
  assert.deepEqual(
    EVALUATION_METRICS.map((m) => m.label),
    ['Faithfulness', 'Answer Relevancy', 'Context Precision', 'Context Recall']
  );
});

test('disabled and not-applicable evaluations are hidden, never shown as zeros', () => {
  assert.equal(shouldShowEvaluation({ enabled: false, status: 'disabled' }), false);
  assert.equal(shouldShowEvaluation({ ...running, status: 'not_applicable' }), false);
  assert.equal(shouldShowEvaluation(undefined), false);
  assert.equal(shouldShowEvaluation(running), true);
});

test('metric events update individual tiles with 0.00-1.00 formatting', () => {
  let ev = applyEvaluationEvent(running, 'evaluation_metric', {
    type: 'evaluation_metric', metric: 'faithfulness', score: 0.9167, status: 'completed', error: null,
  });
  assert.deepEqual(metricView(ev, 'faithfulness'), {
    state: 'completed', display: '0.92', score: 0.9167, tone: 'good', error: null,
  });
  assert.equal(metricView(ev, 'context_recall').state, 'running');

  ev = applyEvaluationEvent(ev, 'evaluation_metric', {
    metric: 'context_recall', score: 0.0, status: 'completed', error: null,
  });
  assert.equal(metricView(ev, 'context_recall').display, '0.00');
});

test('failed metric is distinct from a zero score', () => {
  const ev = applyEvaluationEvent(running, 'evaluation_metric', {
    metric: 'context_precision', score: null, status: 'failed', error: 'Context precision requires ground truth',
  });
  const view = metricView(ev, 'context_precision');
  assert.equal(view.state, 'failed');
  assert.equal(view.display, 'Failed');
  assert.equal(view.score, null);
  assert.match(view.error, /ground truth/);
});

test('evaluation_done replaces state; lost connection fails only unfinished metrics', () => {
  const done = { ...running, status: 'completed' };
  assert.equal(applyEvaluationEvent(running, 'evaluation_done', done), done);

  const partial = applyEvaluationEvent(running, 'evaluation_metric', {
    metric: 'answer_relevancy', score: 0.8, status: 'completed', error: null,
  });
  const lost = applyEvaluationEvent(partial, 'connection_lost', {});
  assert.equal(lost.status, 'failed');
  assert.equal(metricView(lost, 'answer_relevancy').display, '0.80');
  assert.equal(metricView(lost, 'faithfulness').state, 'failed');
});
