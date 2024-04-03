# Changelog

All notable changes to this project will be documented in this file.

## [2024-03-22]: Add fields to cover content of SWE-Bench
Fields in common are left with their current name and missing fields (*) are added
with one exception: test_command is changed to "FAIL_TO_PASS", which is just a 
json list of test commands.

Sampler             SWE-Bench
- title        
- description 
- id                instance_id
- parent_id 
- repo              repo
-                   environment_setup_commit *
- merge_base        base_commit
- diff_merge_base   
- diff_active 
- message_history 
- message_prompt    problem_statement
                    hint_text *
- message_edit 
- context 
- diff_edit         patch
                    test_patch *
- test_command      FAIL_TO_PASS
                    PASS_TO_PASS *
- version 
-                   version
-                   created_at
