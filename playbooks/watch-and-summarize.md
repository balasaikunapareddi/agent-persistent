# Playbook: watch-and-summarize
Watch a source for changes, summarize what changed, and notify via the local outbox.
## Step 1: check_source - Read the source, hash it, and compare with the last seen hash
## Step 2: summarize_change - Summarize what changed compared with the previous content
## Step 3: notify_user - Write a notification to the local outbox about the change
## Step 4: complete - Mark the goal complete
