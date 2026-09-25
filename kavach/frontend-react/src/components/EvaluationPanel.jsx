import React from 'react';
import { EVALUATION_METRICS, metricView, shouldShowEvaluation } from '../utils/evaluation.js';

export default function EvaluationPanel({ evaluation }) {
  if (!shouldShowEvaluation(evaluation)) return null;

  let statusLabel = 'Completed';
  if (evaluation.status === 'running') {
    statusLabel = evaluation.stage?.name === 'ground_truth' && evaluation.stage?.status === 'running'
      ? 'Generating reference answer…'
      : 'Scoring…';
  } else if (evaluation.status === 'failed') {
    statusLabel = 'Failed';
  }

  return (
    <div className="card evaluation-card">
      <div className="evaluation-header">
        <p className="section-label">RAG Evaluation</p>
        <span className={`evaluation-status evaluation-status-${evaluation.status}`}>{statusLabel}</span>
      </div>
      <div className="evaluation-grid">
        {EVALUATION_METRICS.map(({ key, label, hint }) => {
          const view = metricView(evaluation, key);
          return (
            <div
              key={key}
              className={`evaluation-tile evaluation-${view.state} evaluation-tone-${view.tone}`}
              title={view.error || hint}
            >
              <span className="evaluation-metric-label">{label}</span>
              <span className="evaluation-metric-value">{view.display}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
