CREATE DATABASE IF NOT EXISTS financial_doc_review CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE financial_doc_review;


CREATE TABLE approval_workflows (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	workflow_name VARCHAR(128) NOT NULL, 
	document_type VARCHAR(32) NOT NULL, 
	match_conditions_json JSON NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_approval_workflows_document_type ON approval_workflows (document_type);


CREATE TABLE audit_rules (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	rule_code VARCHAR(64) NOT NULL, 
	rule_name VARCHAR(128) NOT NULL, 
	rule_category VARCHAR(64) NOT NULL, 
	threshold JSON NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
)

;

CREATE UNIQUE INDEX ix_audit_rules_rule_code ON audit_rules (rule_code);


CREATE TABLE market_price_references (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	item_name VARCHAR(128) NOT NULL, 
	specification VARCHAR(128) NOT NULL, 
	region VARCHAR(64) NOT NULL, 
	price_min NUMERIC(18, 2) NOT NULL, 
	price_max NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	source_name VARCHAR(128) NOT NULL, 
	effective_date DATE, 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_market_price_references_item_name ON market_price_references (item_name);


CREATE TABLE permissions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	permission_code VARCHAR(64) NOT NULL, 
	permission_name VARCHAR(64) NOT NULL, 
	resource_type VARCHAR(32) NOT NULL, 
	action_type VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (permission_code)
)

;


CREATE TABLE roles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	role_code VARCHAR(32) NOT NULL, 
	role_name VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
)

;

CREATE UNIQUE INDEX ix_roles_role_code ON roles (role_code);


CREATE TABLE supplier_profiles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	supplier_code VARCHAR(64) NOT NULL, 
	supplier_name VARCHAR(128) NOT NULL, 
	credit_status VARCHAR(32) NOT NULL, 
	blacklist_status VARCHAR(16) NOT NULL, 
	risk_tags_json JSON NOT NULL, 
	bank_accounts_json JSON NOT NULL, 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
)

;

CREATE UNIQUE INDEX ix_supplier_profiles_supplier_code ON supplier_profiles (supplier_code);


CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(64) NOT NULL, 
	display_name VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id)
)

;

CREATE UNIQUE INDEX ix_users_username ON users (username);


CREATE TABLE approval_workflow_nodes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	workflow_id INTEGER NOT NULL, 
	node_name VARCHAR(64) NOT NULL, 
	node_order INTEGER NOT NULL, 
	approver_role VARCHAR(32) NOT NULL, 
	approval_mode VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(workflow_id) REFERENCES approval_workflows (id)
)

;

CREATE INDEX ix_approval_workflow_nodes_workflow_id ON approval_workflow_nodes (workflow_id);


CREATE TABLE audit_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	action_type VARCHAR(64) NOT NULL, 
	resource_type VARCHAR(64) NOT NULL, 
	resource_id VARCHAR(64) NOT NULL, 
	detail_json JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);

CREATE INDEX ix_audit_logs_action_type ON audit_logs (action_type);


CREATE TABLE financial_documents (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	document_type VARCHAR(32) NOT NULL, 
	document_no VARCHAR(64) NOT NULL, 
	applicant_id INTEGER NOT NULL, 
	applicant_department VARCHAR(64) NOT NULL, 
	budget_department VARCHAR(64) NOT NULL, 
	payee_name VARCHAR(128) NOT NULL, 
	payee_account VARCHAR(64) NOT NULL, 
	expense_category VARCHAR(64) NOT NULL, 
	total_amount NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	apply_date DATE, 
	reason_text TEXT NOT NULL, 
	document_status VARCHAR(32) NOT NULL, 
	current_version INTEGER NOT NULL, 
	extra_fields_json JSON NOT NULL, 
	version_snapshot JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(applicant_id) REFERENCES users (id)
)

;

CREATE INDEX ix_doc_type_status ON financial_documents (document_type, document_status);

CREATE INDEX ix_financial_documents_document_type ON financial_documents (document_type);

CREATE INDEX ix_financial_documents_document_status ON financial_documents (document_status);

CREATE UNIQUE INDEX ix_financial_documents_document_no ON financial_documents (document_no);

CREATE INDEX ix_financial_documents_applicant_id ON financial_documents (applicant_id);


CREATE TABLE review_sessions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	document_type VARCHAR(32), 
	document_no VARCHAR(64), 
	session_status VARCHAR(32) NOT NULL, 
	confirmed_slots JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)

;

CREATE INDEX ix_review_sessions_user_id ON review_sessions (user_id);


CREATE TABLE role_permissions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	role_id INTEGER NOT NULL, 
	permission_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_role_perm UNIQUE (role_id, permission_id), 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
	FOREIGN KEY(permission_id) REFERENCES permissions (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_role_permissions_permission_id ON role_permissions (permission_id);

CREATE INDEX ix_role_permissions_role_id ON role_permissions (role_id);


CREATE TABLE user_roles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	role_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_role UNIQUE (user_id, role_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_user_roles_role_id ON user_roles (role_id);

CREATE INDEX ix_user_roles_user_id ON user_roles (user_id);


CREATE TABLE analysis_tasks (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	session_id INTEGER, 
	document_id INTEGER NOT NULL, 
	task_status VARCHAR(32) NOT NULL, 
	current_step VARCHAR(64) NOT NULL, 
	progress INTEGER NOT NULL, 
	started_at DATETIME NOT NULL DEFAULT now(), 
	finished_at DATETIME, 
	error_message TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES review_sessions (id), 
	FOREIGN KEY(document_id) REFERENCES financial_documents (id)
)

;

CREATE INDEX ix_analysis_tasks_document_id ON analysis_tasks (document_id);


CREATE TABLE approval_instances (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	workflow_id INTEGER NOT NULL, 
	document_id INTEGER NOT NULL, 
	document_version INTEGER NOT NULL, 
	instance_status VARCHAR(32) NOT NULL, 
	current_node_id INTEGER, 
	started_at DATETIME NOT NULL DEFAULT now(), 
	finished_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workflow_id) REFERENCES approval_workflows (id), 
	FOREIGN KEY(document_id) REFERENCES financial_documents (id)
)

;

CREATE INDEX ix_approval_instances_workflow_id ON approval_instances (workflow_id);

CREATE INDEX ix_approval_instances_document_id ON approval_instances (document_id);


CREATE TABLE document_attachments (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	document_id INTEGER NOT NULL, 
	document_version INTEGER NOT NULL, 
	file_name VARCHAR(255) NOT NULL, 
	file_type VARCHAR(16) NOT NULL, 
	file_size INTEGER NOT NULL, 
	file_path VARCHAR(512) NOT NULL, 
	file_hash VARCHAR(64) NOT NULL, 
	storage_status VARCHAR(16) NOT NULL, 
	parse_status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES financial_documents (id)
)

;

CREATE INDEX ix_document_attachments_document_id ON document_attachments (document_id);


CREATE TABLE document_line_items (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	document_id INTEGER NOT NULL, 
	item_type VARCHAR(32) NOT NULL, 
	item_name VARCHAR(128) NOT NULL, 
	expense_date DATE, 
	expense_location VARCHAR(128) NOT NULL, 
	quantity NUMERIC(18, 4) NOT NULL, 
	unit_price NUMERIC(18, 2) NOT NULL, 
	amount NUMERIC(18, 2) NOT NULL, 
	remark VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES financial_documents (id)
)

;

CREATE INDEX ix_document_line_items_document_id ON document_line_items (document_id);

CREATE INDEX ix_line_item_document ON document_line_items (document_id, item_type);


CREATE TABLE document_status_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	document_id INTEGER NOT NULL, 
	from_status VARCHAR(32) NOT NULL, 
	to_status VARCHAR(32) NOT NULL, 
	operator_id INTEGER, 
	remark VARCHAR(255) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES financial_documents (id), 
	FOREIGN KEY(operator_id) REFERENCES users (id)
)

;

CREATE INDEX ix_document_status_logs_document_id ON document_status_logs (document_id);


CREATE TABLE document_versions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	document_id INTEGER NOT NULL, 
	version_no INTEGER NOT NULL, 
	document_snapshot_json JSON NOT NULL, 
	created_by INTEGER, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	updated_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_doc_version UNIQUE (document_id, version_no), 
	FOREIGN KEY(document_id) REFERENCES financial_documents (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
)

;

CREATE INDEX ix_document_versions_document_id ON document_versions (document_id);


CREATE TABLE session_messages (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	session_id INTEGER NOT NULL, 
	`role` VARCHAR(16) NOT NULL, 
	content TEXT NOT NULL, 
	message_type VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES review_sessions (id)
)

;

CREATE INDEX ix_session_messages_session_id ON session_messages (session_id);


CREATE TABLE approval_tasks (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	instance_id INTEGER NOT NULL, 
	node_id INTEGER NOT NULL, 
	approver_id INTEGER, 
	task_status VARCHAR(32) NOT NULL, 
	review_comment TEXT NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	processed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(instance_id) REFERENCES approval_instances (id), 
	FOREIGN KEY(node_id) REFERENCES approval_workflow_nodes (id), 
	FOREIGN KEY(approver_id) REFERENCES users (id)
)

;

CREATE INDEX ix_approval_tasks_instance_id ON approval_tasks (instance_id);

CREATE INDEX ix_approval_tasks_node_id ON approval_tasks (node_id);


CREATE TABLE attachment_parse_results (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	attachment_id INTEGER NOT NULL, 
	document_category VARCHAR(32) NOT NULL, 
	full_text TEXT NOT NULL, 
	fields_json JSON NOT NULL, 
	evidence_positions_json JSON NOT NULL, 
	confidence NUMERIC(5, 4) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(attachment_id) REFERENCES document_attachments (id)
)

;

CREATE UNIQUE INDEX ix_attachment_parse_results_attachment_id ON attachment_parse_results (attachment_id);


CREATE TABLE invoice_records (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	attachment_id INTEGER NOT NULL, 
	invoice_code VARCHAR(64) NOT NULL, 
	invoice_no VARCHAR(64) NOT NULL, 
	seller_name VARCHAR(128) NOT NULL, 
	buyer_name VARCHAR(128) NOT NULL, 
	invoice_date DATE, 
	amount_excluding_tax NUMERIC(18, 2) NOT NULL, 
	tax_amount NUMERIC(18, 2) NOT NULL, 
	amount_including_tax NUMERIC(18, 2) NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(attachment_id) REFERENCES document_attachments (id)
)

;

CREATE INDEX ix_invoice_records_attachment_id ON invoice_records (attachment_id);


CREATE TABLE review_reports (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	task_id INTEGER NOT NULL, 
	document_id INTEGER NOT NULL, 
	overall_risk_level VARCHAR(16) NOT NULL, 
	risk_summary_json JSON NOT NULL, 
	amount_comparison_json JSON NOT NULL, 
	recommendation VARCHAR(32) NOT NULL, 
	report_markdown TEXT NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES analysis_tasks (id), 
	FOREIGN KEY(document_id) REFERENCES financial_documents (id)
)

;

CREATE INDEX ix_review_reports_task_id ON review_reports (task_id);

CREATE INDEX ix_review_reports_document_id ON review_reports (document_id);


CREATE TABLE risk_findings (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	task_id INTEGER NOT NULL, 
	risk_type VARCHAR(64) NOT NULL, 
	risk_level VARCHAR(16) NOT NULL, 
	risk_title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	actual_value_json JSON NOT NULL, 
	reference_value_json JSON NOT NULL, 
	threshold_json JSON NOT NULL, 
	evidence_json JSON NOT NULL, 
	suggestion_text TEXT NOT NULL, 
	review_status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES analysis_tasks (id)
)

;

CREATE INDEX ix_risk_findings_risk_type ON risk_findings (risk_type);

CREATE INDEX ix_risk_findings_task_id ON risk_findings (task_id);


CREATE TABLE manual_reviews (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	report_id INTEGER NOT NULL, 
	reviewer_id INTEGER NOT NULL, 
	review_result VARCHAR(32) NOT NULL, 
	review_comment TEXT NOT NULL, 
	reviewed_at DATETIME NOT NULL DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(report_id) REFERENCES review_reports (id), 
	FOREIGN KEY(reviewer_id) REFERENCES users (id)
)

;

CREATE INDEX ix_manual_reviews_report_id ON manual_reviews (report_id);

CREATE INDEX ix_manual_reviews_reviewer_id ON manual_reviews (reviewer_id);
