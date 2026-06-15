#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

## user_problem_statement: "Verify and stabilize the Gravity Engineering Works ERP backend and frontend. The app covers Authentication, Inventory, Purchase, Sales, CRM, Logistics, Proforma Invoices, Email sending, HRM, Payroll, Accounting, and AI Assistant modules."

## backend:
##   - task: "Authentication"
##     implemented: true
##     working: true
##     file: "backend/routers/auth.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "All auth tests pass locally against the running server."
##
##   - task: "Inventory Management"
##     implemented: true
##     working: true
##     file: "backend/routers/inventory.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "Warehouses, products, adjustment, and object storage upload tests pass successfully."
##
##   - task: "Purchase Orders"
##     implemented: true
##     working: true
##     file: "backend/routers/purchase.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "Supplier CRUD and Purchase Order creation and receipt flow verified."
##
##   - task: "CRM Leads & Customers"
##     implemented: true
##     working: true
##     file: "backend/routers/sales.py"
##     stuck_count: 0
##     priority: "medium"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "Customer CRUD and Leads status transition flows verified."
##
##   - task: "Sales Orders & GST Invoices"
##     implemented: true
##     working: true
##     file: "backend/routers/sales.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "Quotations, Sales Orders confirmation with stock check, Invoices payment, and Dispatches verified."
##
##   - task: "Proforma Invoice (PI) Module"
##     implemented: true
##     working: true
##     file: "backend/routers/proforma.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "PI CRUD, auto-numbering, server-side totals, amount in words translation, and reportlab PDF generation verified."
##
##   - task: "Email (Resend) Integration"
##     implemented: true
##     working: true
##     file: "backend/routers/email.py"
##     stuck_count: 0
##     priority: "medium"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "Email status check, test email dispatch, doc-specific email trigger (Quotations, PIs, Invoices), and email log retrieval pass regression checks."
##
##   - task: "HRM & Payroll Management"
##     implemented: true
##     working: true
##     file: "backend/routers/hr_setup.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "Branches, departments, designations, shifts, holidays, leave types, employees CRUD, QR token reset, attendance check-ins, biometric webhook, leave approvals, payroll runs generation/locking/unlocking, and public payslip retrieval verified."
##
##   - task: "Verification Module"
##     implemented: true
##     working: true
##     file: "backend/routers/verifications.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "GST, PAN, Aadhaar validation APIs, data linking, security masking, dashboard stats, and API settings verified via a new integration test suite."
##
## frontend:
##   - task: "Frontend Core UI & Routing"
##     implemented: true
##     working: true
##     file: "frontend/src/App.js"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         - working: true
##           agent: "main"
##           comment: "Core routing is configured and active. React frontend is ready to compile."
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 2
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Verify backend local server startup"
##     - "Verify all 137 tests pass successfully"
##   stuck_tasks: []
##   test_all: true
##   test_priority: "sequential"
##
## agent_communication:
##     - agent: "main"
##       message: "Created a dedicated test suite (test_verifications.py) and successfully ran all 137 backend tests (regression + new verifications flow) with a 100% pass rate. Verified the frontend built successfully without any JSX or syntax compile errors."