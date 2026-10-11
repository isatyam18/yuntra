# Five-minute quickstart

1. Install from the repository root:

   ```powershell
   py -m pip install -e .
   yuntra init
   ```

2. Register a repository:

   ```powershell
   yuntra project create --name "Demo" --repository C:\src\demo
   yuntra plan edit demo
   ```

3. Fill in the printed `PROJECT_SPEC.md` manually. Then review and approve it:

   ```powershell
   yuntra plan review demo
   yuntra plan approve demo --yes
   ```

4. Save and recover a checkpoint:

   ```powershell
   yuntra checkpoint save demo --next-action "Start the first approved task"
   yuntra resume demo
   ```

5. Inspect the canonical state:

   ```powershell
   yuntra status demo
   yuntra dashboard demo
   ```

Yuntra stores data in `%LOCALAPPDATA%\Yuntra` unless `YUNTRA_HOME` is set. It never auto-commits or pushes.
