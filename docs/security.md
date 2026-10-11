# Security model

Project profiles default to denying automatic commits, Git pushes, dependency installation, network operations, and destructive file operations. The current MVP invokes only user-supplied verification commands after approval. Common inline credential assignments are redacted before Yuntra persists event, decision, lesson, verification, checkpoint, and adapter-output metadata. Plan review rejects specifications that appear to contain a credential. Adapter output is not trusted as repository evidence.
