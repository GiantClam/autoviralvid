# Skills Database Setup Guide

## Quick Start

### Step 1: Run the Database Migration

1. Open your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Click **New Query**
4. Copy the entire contents of `agent/src/migrations/001_skills_tables.sql`
5. Paste into the SQL Editor
6. Click **Run** (or press Ctrl+Enter)

You should see a success message indicating that:
- 4 tables were created
- 4 skills were inserted

### Step 2: Verify the Migration

In the Supabase dashboard:

1. Go to **Table Editor**
2. Check that these tables exist:
   - `skills`
   - `skill_executions`
   - `user_skill_preferences`
   - `skill_discovery_cache`

3. Click on the `skills` table
4. Verify that 4 rows exist:
   - `runninghub_sora2_i2v` (RunningHub Sora2 Video)
   - `tokenengine_sora2` (TokenEngine Sora2)
   - `zhenzhen_sora2` (ZhenZhen Sora2)
   - `runninghub_qwen_t2i` (RunningHub Qwen Scene Image)

### Step 3: Verify Environment Variables

Check your `agent/.env` file contains:

```env
# RunningHub Configuration
RUNNINGHUB_API_KEY=your_api_key_here
RUNNINGHUB_SORA2_WORKFLOW_ID=1985261217524629506

# Supabase Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

### Step 4: Test the Skills System

Run the test script:

```bash
cd agent
python -m src.test_skills
```

Expected output:
```
✓ Skills registry initialized successfully
✓ Loaded 4 skills from database
✓ Found skill: RunningHub Sora2 Video
✓ Selected 3 skill(s)
✓ RunningHub Sora2 is in the selection

🎉 All tests passed!
```

### Step 5: Restart the Agent Server

```bash
pnpm dev:agent
```

You should no longer see the error:
```
Failed to load skills from database: {'message': 'relation "public.skills" does not exist'
```

## Troubleshooting

### Error: "relation does not exist"
- **Cause**: Migration hasn't been run
- **Solution**: Follow Step 1 above

### Error: "No skills found in database"
- **Cause**: Seed data wasn't inserted
- **Solution**: Re-run the migration SQL

### Error: "RUNNINGHUB_API_KEY not configured"
- **Cause**: Missing environment variable
- **Solution**: Add `RUNNINGHUB_API_KEY` to `agent/.env`

### Skills not being used in video generation
- **Cause**: Skills system may be falling back to legacy providers
- **Solution**: Check logs for "Using Skills system" vs "Using legacy provider"

## What Was Created

### Database Tables

1. **`skills`**: Registry of all available skills
   - Stores skill metadata, capabilities, and configuration
   - Includes node mappings for ComfyUI workflows

2. **`skill_executions`**: Execution history
   - Tracks every skill execution
   - Records success/failure, duration, and quality metrics

3. **`user_skill_preferences`**: User preferences
   - Stores user-specific skill preferences
   - Allows customization of quality/speed/cost tradeoffs

4. **`skill_discovery_cache`**: Marketplace cache
   - For future skill marketplace integration

### Initial Skills

1. **RunningHub Sora2** (Priority 10 - Highest)
   - High-quality video generation
   - Uses ComfyUI workflow
   - Supports 5-10 second videos

2. **TokenEngine Sora2** (Priority 20)
   - Fast video generation
   - Direct API integration

3. **ZhenZhen Sora2** (Priority 30)
   - Budget-friendly option
   - Direct API integration

4. **RunningHub Qwen** (Priority 10)
   - Scene image generation
   - Product reference support

## Next Steps

Once the migration is complete:

1. ✅ Skills will be automatically loaded from the database
2. ✅ The skill selector will choose the best skill based on requirements
3. ✅ Execution history will be tracked for quality improvement
4. 🔜 Add more skills via Supabase dashboard or API
5. 🔜 Customize skill priorities and preferences
