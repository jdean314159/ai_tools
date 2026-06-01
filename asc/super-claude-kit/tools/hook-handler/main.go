// Super Claude Kit - Hook Handler
// A fast, unified hook handler for Claude Code
// Replaces slow bash scripts with a single Go binary
package main
import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)
const version = "1.0.0"
// HookInput represents the JSON input from Claude Code
type HookInput struct {
	// Common fields
	SessionID string `json:"session_id,omitempty"`
	// PreToolUse / PostToolUse fields
	ToolName  string                 `json:"tool_name,omitempty"`
	ToolInput map[string]interface{} `json:"tool_input,omitempty"`
	// PostToolUse additional fields
	ToolResponse interface{} `json:"tool_response,omitempty"`
	// UserPromptSubmit fields
	Prompt string `json:"prompt,omitempty"`
	// Stop hook fields
	StopHookActive bool `json:"stop_hook_active,omitempty"`
}
// HookOutput represents the JSON output to Claude Code
type HookOutput struct {
	SystemMessage      string                 `json:"systemMessage,omitempty"`
	HookSpecificOutput map[string]interface{} `json:"hookSpecificOutput,omitempty"`
}
// Config holds runtime configuration
type Config struct {
	ProjectDir        string
	SessionDir        string
	SessionID         string
	WorkerProfile     string
	AllowedTools      []string
	AgentMailbox      string
	RegisterWithMail  bool
	UsesBeads         bool
	TempPrefix        string
	QuietMode         bool
}
var config Config
func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "Usage: hook-handler <hook-type> [options]")
		fmt.Fprintln(os.Stderr, "Hook types: pre-tool-use, post-tool-use, user-prompt-submit, stop, session-start, session-end")
		os.Exit(1)
	}
	hookType := os.Args[1]
	// Handle version flag
	if hookType == "--version" || hookType == "-v" {
		fmt.Printf("hook-handler %s\n", version)
		os.Exit(0)
	}
	// Initialize config from environment
	initConfig()
	// Read JSON input from stdin
	input, err := readInput()
	if err != nil {
		// Silent exit on input errors - don't corrupt Claude's output
		os.Exit(0)
	}
	// Route to appropriate handler
	var output *HookOutput
	switch hookType {
	case "pre-tool-use":
		output = handlePreToolUse(input)
	case "post-tool-use":
		output = handlePostToolUse(input)
	case "user-prompt-submit":
		output = handleUserPromptSubmit(input)
	case "stop":
		output = handleStop(input)
	case "session-start":
		output = handleSessionStart(input)
	case "session-end":
		output = handleSessionEnd(input)
	default:
		os.Exit(0)
	}
	// Output JSON response if any
	if output != nil {
		jsonBytes, err := json.Marshal(output)
		if err == nil {
			fmt.Println(string(jsonBytes))
		}
	}
}
func initConfig() {
	config.WorkerProfile = getEnv("CLAUDE_WORKER_PROFILE", "default")
	config.SessionID = getEnv("CLAUDE_SESSION_ID", config.WorkerProfile)
	config.ProjectDir = findProjectRoot()
	config.SessionDir = filepath.Join(config.ProjectDir, ".claude", "sessions", config.SessionID)
	config.QuietMode = getEnv("CLAUDE_QUIET_HOOKS", "false") == "true"
	config.AgentMailbox = os.Getenv("CLAUDE_AGENT_MAILBOX")
	config.RegisterWithMail = getEnv("CLAUDE_WORKER_REGISTER_WITH_MAIL", "false") == "true"
	config.TempPrefix = getEnv("CLAUDE_WORKER_TEMP_PREFIX", slugify(config.WorkerProfile))
	// Parse allowed tools from JSON
	allowedJSON := os.Getenv("CLAUDE_WORKER_ALLOWED_TOOLS")
	if allowedJSON != "" {
		json.Unmarshal([]byte(allowedJSON), &config.AllowedTools)
	}
	// Ensure session directory exists
	os.MkdirAll(config.SessionDir, 0755)
}
func readInput() (*HookInput, error) {
	// Fast stdin read - just read all available data
	inputBytes, err := io.ReadAll(os.Stdin)
	if err != nil {
		return nil, err
	}
	if len(inputBytes) == 0 {
		return &HookInput{}, nil
	}
	var input HookInput
	if err := json.Unmarshal(inputBytes, &input); err != nil {
		return nil, err
	}
	return &input, nil
}
// ============================================================================
// PRE-TOOL-USE HANDLER
// ============================================================================
func handlePreToolUse(input *HookInput) *HookOutput {
	if input.ToolName == "" {
		return nil
	}
	var contexts []string
	// 1. Check tool permissions
	if len(config.AllowedTools) > 0 {
		if !isToolAllowed(input.ToolName) {
			return &HookOutput{
				HookSpecificOutput: map[string]interface{}{
					"hookEventName":            "PreToolUse",
					"permissionDecision":       "deny",
					"permissionDecisionReason": fmt.Sprintf("Tool '%s' not permitted by worker profile (%s)", input.ToolName, config.WorkerProfile),
				},
			}
		}
	}
	// 2. Large file warning for Read tool
	if input.ToolName == "Read" {
		if filePath, ok := input.ToolInput["file_path"].(string); ok && filePath != "" {
			if info, err := os.Stat(filePath); err == nil {
				sizeKB := info.Size() / 1024
				if sizeKB > 50 {
					contexts = append(contexts, fmt.Sprintf(
						"[LARGE FILE WARNING] File size: %dKB exceeds 50KB threshold. Consider using progressive-reader:\n"+
							"- Preview: .claude/bin/progressive-reader --path %s --list\n"+
							"- Read chunk: .claude/bin/progressive-reader --path %s --chunk N",
						sizeKB, filePath, filePath))
				}
			}
			// 3. Redundant read detection
			if warning := checkRedundantRead(filePath); warning != "" {
				contexts = append(contexts, warning)
			}
		}
	}
	// 4. Task tool suggestions for dependency queries
	if input.ToolName == "Task" {
		if prompt, ok := input.ToolInput["prompt"].(string); ok {
			promptLower := strings.ToLower(prompt)
			if containsAny(promptLower, []string{"depend", "import", "require", "circular", "who.*use", "what.*import"}) {
				contexts = append(contexts, "[TOOL SUGGESTION] Query appears to be about code dependencies. Consider using specialized tools:\n"+
					"- query-deps: bash .claude/tools/query-deps/query-deps.sh <file-path>\n"+
					"- impact-analysis: bash .claude/tools/impact-analysis/impact-analysis.sh <file-path>\n"+
					"- find-circular: bash .claude/tools/find-circular/find-circular.sh")
			}
		}
	}
	if len(contexts) > 0 {
		return &HookOutput{
			HookSpecificOutput: map[string]interface{}{
				"hookEventName":      "PreToolUse",
				"permissionDecision": "allow",
				"additionalContext":  strings.Join(contexts, "\n\n"),
			},
		}
	}
	return nil
}
func isToolAllowed(toolName string) bool {
	if len(config.AllowedTools) == 0 {
		return true
	}
	toolNorm := canonicalToolName(toolName)
	for _, allowed := range config.AllowedTools {
		allowedNorm := canonicalToolName(allowed)
		if allowedNorm == "*" || allowedNorm == "all" || allowedNorm == toolNorm {
			return true
		}
	}
	return false
}
func canonicalToolName(name string) string {
	lower := strings.ToLower(strings.TrimSpace(name))
	mapping := map[string]string{
		"execute": "bash", "shell": "bash", "command": "bash",
		"todo-write": "todowrite", "todo_write": "todowrite",
	}
	if mapped, ok := mapping[lower]; ok {
		return mapped
	}
	return lower
}
func checkRedundantRead(filePath string) string {
	recentReadsLog := filepath.Join(config.SessionDir, "recent_reads.log")
	warningsShown := filepath.Join(config.SessionDir, "read_warnings_shown.log")
	// Check if already warned
	if fileContainsLine(warningsShown, filePath) {
		return ""
	}
	// Check recent reads
	threshold := int64(300) // 5 minutes
	currentTime := time.Now().Unix()
	if lastRead := getLastReadTime(recentReadsLog, filePath); lastRead > 0 {
		timeSince := currentTime - lastRead
		if timeSince < threshold && timeSince > 0 {
			// Record warning shown
			appendToFile(warningsShown, filePath)
			timeStr := fmt.Sprintf("%ds", timeSince)
			if timeSince >= 60 {
				timeStr = fmt.Sprintf("%dm", timeSince/60)
			}
			return fmt.Sprintf("[REDUNDANT READ] File '%s' was read %s ago. Check capsule context first.", filePath, timeStr)
		}
	}
	// Record this read
	appendToFile(recentReadsLog, fmt.Sprintf("%s,%d", filePath, currentTime))
	return ""
}
// ============================================================================
// POST-TOOL-USE HANDLER
// ============================================================================
func handlePostToolUse(input *HookInput) *HookOutput {
	if input.ToolName == "" {
		return nil
	}
	// Log file access for Read/Edit/Write
	switch input.ToolName {
	case "Read", "Edit", "Write":
		if filePath, ok := input.ToolInput["file_path"].(string); ok && filePath != "" {
			logFileAccess(filePath, strings.ToLower(input.ToolName))
		}
	case "Task":
		// Log subagent completion
		if agentType, ok := input.ToolInput["subagent_type"].(string); ok && agentType != "" {
			summary := extractResponseSummary(input.ToolResponse)
			logSubagent(agentType, summary)
		}
	case "TodoWrite":
		// Sync todo changes to session log
		syncTodoWrite(input.ToolInput)
	}
	return nil
}
func logFileAccess(filePath, action string) {
	// Log to session file
	sessionLog := filepath.Join(config.SessionDir, "session_files.log")
	entry := fmt.Sprintf("%d|%s|%s|%s", time.Now().Unix(), config.WorkerProfile, action, filePath)
	appendToFile(sessionLog, entry)
	// Log to shared hive memory
	sharedLog := filepath.Join(config.ProjectDir, ".claude", "shared", "file_access.jsonl")
	jsonEntry := map[string]interface{}{
		"timestamp": time.Now().Unix(),
		"profile":   config.WorkerProfile,
		"action":    action,
		"file":      filePath,
	}
	if jsonBytes, err := json.Marshal(jsonEntry); err == nil {
		appendToFile(sharedLog, string(jsonBytes))
	}
}
func logSubagent(agentType, summary string) {
	sessionLog := filepath.Join(config.SessionDir, "session_subagents.log")
	entry := fmt.Sprintf("%d|%s|%s", time.Now().Unix(), agentType, truncate(summary, 200))
	appendToFile(sessionLog, entry)
	// Log to shared
	sharedLog := filepath.Join(config.ProjectDir, ".claude", "shared", "subagents.jsonl")
	jsonEntry := map[string]interface{}{
		"timestamp": time.Now().Unix(),
		"profile":   config.WorkerProfile,
		"agent":     agentType,
		"summary":   truncate(summary, 200),
	}
	if jsonBytes, err := json.Marshal(jsonEntry); err == nil {
		appendToFile(sharedLog, string(jsonBytes))
	}
}
func syncTodoWrite(toolInput map[string]interface{}) {
	taskLog := filepath.Join(config.SessionDir, "current_tasks.log")
	// Clear existing tasks
	os.WriteFile(taskLog, []byte{}, 0644)
	todos, ok := toolInput["todos"].([]interface{})
	if !ok {
		return
	}
	var entries []string
	for _, todo := range todos {
		if todoMap, ok := todo.(map[string]interface{}); ok {
			status, _ := todoMap["status"].(string)
			content, _ := todoMap["content"].(string)
			if content != "" {
				entries = append(entries, fmt.Sprintf("%s|%s", status, content))
			}
		}
	}
	if len(entries) > 0 {
		os.WriteFile(taskLog, []byte(strings.Join(entries, "\n")), 0644)
	}
	// Log to shared
	sharedLog := filepath.Join(config.ProjectDir, ".claude", "shared", "tasks.jsonl")
	jsonEntry := map[string]interface{}{
		"timestamp": time.Now().Unix(),
		"profile":   config.WorkerProfile,
		"todos":     todos,
	}
	if jsonBytes, err := json.Marshal(jsonEntry); err == nil {
		appendToFile(sharedLog, string(jsonBytes))
	}
}
func extractResponseSummary(response interface{}) string {
	if response == nil {
		return ""
	}
	switch v := response.(type) {
	case string:
		return truncate(v, 200)
	case map[string]interface{}:
		if content, ok := v["content"].(string); ok {
			return truncate(content, 200)
		}
		if result, ok := v["result"].(string); ok {
			return truncate(result, 200)
		}
	}
	return ""
}
// ============================================================================
// USER-PROMPT-SUBMIT HANDLER
// ============================================================================
func handleUserPromptSubmit(input *HookInput) *HookOutput {
	if config.QuietMode {
		return nil
	}
	var contexts []string
	// 1. Check for Agent Mail alerts
	alertFile := filepath.Join(config.SessionDir, "agent_mail_alert.txt")
	if content, err := os.ReadFile(alertFile); err == nil && len(content) > 0 {
		contexts = append(contexts, fmt.Sprintf("[AGENT MAIL ALERT] You have unread messages:\n%s\nProcess inbox and run: ./.claude/hooks/ack-worker-mail-alert.sh", string(content)))
	}
	// 2. Contextual suggestions based on prompt keywords
	if input.Prompt != "" && len(input.Prompt) >= 10 {
		promptLower := strings.ToLower(input.Prompt)
		suggestionsShown := filepath.Join(config.SessionDir, "suggestions_shown.log")
		// Exploration tasks
		if containsAny(promptLower, []string{"explore", "find.*file", "search.*code", "where.*is", "how does.*work"}) {
			if !fileContainsLine(suggestionsShown, "explore") {
				contexts = append(contexts, "[SUGGESTION] Use Task tool with subagent_type='Explore' for fast codebase exploration")
				appendToFile(suggestionsShown, "explore")
			}
		}
		// Planning tasks
		if containsAny(promptLower, []string{"plan", "implement", "build", "create", "develop", "design"}) {
			if !fileContainsLine(suggestionsShown, "plan") {
				contexts = append(contexts, "[SUGGESTION] Use Task tool with subagent_type='Plan' for systematic implementation")
				appendToFile(suggestionsShown, "plan")
			}
		}
		// TodoWrite reminder
		if containsAny(promptLower, []string{"implement", "build", "create", "fix.*bug", "add.*feature", "refactor"}) {
			if !fileContainsLine(suggestionsShown, "todowrite") {
				contexts = append(contexts, "[REMINDER] Use TodoWrite for multi-step tasks")
				appendToFile(suggestionsShown, "todowrite")
			}
		}
	}
	// Track message count
	countFile := filepath.Join(config.SessionDir, "message_count.txt")
	count := 1
	if content, err := os.ReadFile(countFile); err == nil {
		fmt.Sscanf(string(content), "%d", &count)
		count++
	}
	os.WriteFile(countFile, []byte(fmt.Sprintf("%d", count)), 0644)
	if len(contexts) > 0 {
		return &HookOutput{
			HookSpecificOutput: map[string]interface{}{
				"hookEventName":     "UserPromptSubmit",
				"additionalContext": strings.Join(contexts, "\n\n"),
			},
		}
	}
	return nil
}
// ============================================================================
// STOP HANDLER
// ============================================================================
func handleStop(input *HookInput) *HookOutput {
	if input.StopHookActive {
		return nil
	}
	suggestionsShown := filepath.Join(config.SessionDir, "quality_suggestions_shown.log")
	if fileContainsLine(suggestionsShown, "stop_quality") {
		return nil
	}
	// Quality check: files accessed vs discoveries logged
	fileLog := filepath.Join(config.SessionDir, "session_files.log")
	discoveryLog := filepath.Join(config.SessionDir, "session_discoveries.log")
	fileCount := countLines(fileLog)
	discoveryCount := countLines(discoveryLog)
	// If 3+ files accessed but 0 discoveries, suggest logging
	if fileCount >= 3 && discoveryCount == 0 {
		appendToFile(suggestionsShown, "stop_quality")
		return &HookOutput{
			SystemMessage: fmt.Sprintf("[QUALITY TIP] Accessed %d files but logged 0 discoveries. Consider: bash .claude/hooks/log-discovery.sh \"<category>\" \"<finding>\"", fileCount),
			HookSpecificOutput: map[string]interface{}{
				"hookEventName": "Stop",
			},
		}
	}
	return nil
}
// ============================================================================
// SESSION START/END HANDLERS
// ============================================================================
func handleSessionStart(input *HookInput) *HookOutput {
	// Create session directory
	os.MkdirAll(config.SessionDir, 0755)
	os.MkdirAll(filepath.Join(config.ProjectDir, ".claude", "shared"), 0755)
	// Build system message
	var parts []string
	parts = append(parts, fmt.Sprintf("Super Claude Kit - Worker: %s", config.WorkerProfile))
	parts = append(parts, fmt.Sprintf("Session: %s", config.SessionID))
	parts = append(parts, fmt.Sprintf("Session Dir: %s", config.SessionDir))
	parts = append(parts, fmt.Sprintf("Temp Prefix: %s", config.TempPrefix))
	// Add temp file guidance
	parts = append(parts, "")
	parts = append(parts, fmt.Sprintf("IMPORTANT: When creating temporary JSON files for Agent Mail or other purposes:"))
	parts = append(parts, fmt.Sprintf("- Use naming pattern: tmp_workermail_%s_<purpose>.json", config.TempPrefix))
	parts = append(parts, fmt.Sprintf("- Create files in the session directory: %s/", config.SessionDir))
	return &HookOutput{
		SystemMessage: strings.Join(parts, "\n"),
		HookSpecificOutput: map[string]interface{}{
			"hookEventName": "SessionStart",
		},
	}
}
func handleSessionEnd(input *HookInput) *HookOutput {
	// Clean up session tracking files
	filesToClean := []string{
		"recent_reads.log",
		"read_warnings_shown.log",
		"suggestions_shown.log",
		"quality_suggestions_shown.log",
		"quality_check_state.txt",
	}
	for _, f := range filesToClean {
		os.Remove(filepath.Join(config.SessionDir, f))
	}
	// Clean up temp files matching pattern
	pattern := fmt.Sprintf("tmp_workermail_%s_*.json", config.TempPrefix)
	matches, _ := filepath.Glob(filepath.Join(config.SessionDir, pattern))
	for _, m := range matches {
		os.Remove(m)
	}
	return nil
}
// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================
func findProjectRoot() string {
	dir, _ := os.Getwd()
	for dir != "/" && dir != "" {
		if _, err := os.Stat(filepath.Join(dir, ".claude")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	// Fall back to current directory
	cwd, _ := os.Getwd()
	return cwd
}
func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}
func slugify(s string) string {
	reg := regexp.MustCompile(`[^a-zA-Z0-9]+`)
	return strings.ToLower(reg.ReplaceAllString(s, "_"))
}
func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen]
}
func containsAny(s string, patterns []string) bool {
	for _, p := range patterns {
		if strings.Contains(p, ".*") {
			// Simple regex pattern
			if matched, _ := regexp.MatchString(p, s); matched {
				return true
			}
		} else if strings.Contains(s, p) {
			return true
		}
	}
	return false
}
func fileContainsLine(filePath, line string) bool {
	content, err := os.ReadFile(filePath)
	if err != nil {
		return false
	}
	for _, l := range strings.Split(string(content), "\n") {
		if strings.TrimSpace(l) == line {
			return true
		}
	}
	return false
}
func getLastReadTime(logFile, filePath string) int64 {
	content, err := os.ReadFile(logFile)
	if err != nil {
		return 0
	}
	var lastTime int64
	for _, line := range strings.Split(string(content), "\n") {
		if strings.HasPrefix(line, filePath+",") {
			parts := strings.Split(line, ",")
			if len(parts) >= 2 {
				var t int64
				fmt.Sscanf(parts[1], "%d", &t)
				if t > lastTime {
					lastTime = t
				}
			}
		}
	}
	return lastTime
}
func appendToFile(filePath, line string) {
	os.MkdirAll(filepath.Dir(filePath), 0755)
	f, err := os.OpenFile(filePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	f.WriteString(line + "\n")
}
func countLines(filePath string) int {
	content, err := os.ReadFile(filePath)
	if err != nil {
		return 0
	}
	lines := strings.Split(strings.TrimSpace(string(content)), "\n")
	if len(lines) == 1 && lines[0] == "" {
		return 0
	}
	return len(lines)
}
