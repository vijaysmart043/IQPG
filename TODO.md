# TODO: Enhance Intelligent EXAM Generation System

## Current Status
- Analyzed codebase and identified key files
- Created comprehensive plan for L1-L6 Bloom's levels and staging workflow changes
- ✅ Updated AI prompt in routes/uploader.py to include L6 (Creating) level
- ✅ Adjusted validation in routes/uploader.py to accept bloom_level 1-6
- ✅ Modified templates/staging.html to replace accept/reject/edit with add/remove buttons
- ✅ Updated Bloom's level options in staging template to include L6
- ✅ Implemented handle_staging_action in routes/questions.py for add/remove workflow
- ✅ Added logic to transfer added questions to syllabus collection
- ✅ Created new route /syllabus-questions in routes/questions.py
- ✅ Created templates/syllabus_questions.html for syllabus questions management

## Pending Tasks
- [ ] Test PDF upload to staging workflow
- [ ] Test add/remove actions in staging
- [ ] Test syllabus questions management page
- [ ] Verify L1-L6 levels are properly handled throughout
