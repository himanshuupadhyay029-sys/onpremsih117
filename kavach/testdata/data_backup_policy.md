# Data Backup and Retention Policy

## Purpose
This policy defines backup scheduling, retention, and recovery objectives for all
production systems.

## Backup Schedule
- Full backups run every Sunday at 02:00 IST.
- Incremental backups run daily at 23:00 IST.
- Backup jobs are monitored by the Infrastructure Team; any failed job must be
  re-run within 4 hours of the failure alert.

## Retention
- Daily incremental backups are retained for 45 days.
- Monthly full backup archives are retained for 1 year.
- Backups older than the retention window are securely purged automatically.

## Recovery Objectives
- Recovery Time Objective (RTO): 4 hours.
- Recovery Point Objective (RPO): 24 hours.

## Restoration Testing
Backup restoration must be tested quarterly by restoring a sample dataset to a
staging environment and verifying data integrity. Results are logged in the
quarterly compliance report.
