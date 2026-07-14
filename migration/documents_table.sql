-- ============================================================
-- Document Tracking System
-- Tracks every document discovered, downloaded, and uploaded
-- during scraping operations across all districts and sources.
-- ============================================================

CREATE TABLE documents (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    -- Identity
    title           VARCHAR(512)    NOT NULL,
    source_url      VARCHAR(2048)   NOT NULL,
    checksum        VARCHAR(64)     NULL COMMENT 'SHA-256 of file contents for dedup',

    -- Classification
    media_type      VARCHAR(50)     NOT NULL COMMENT 'PDF, HTML, video, image, spreadsheet, text, archive, other',
    file_type       VARCHAR(100)    NULL COMMENT 'MIME type: application/pdf, text/html, video/mp4, etc.',
    file_extension  VARCHAR(20)     NULL COMMENT 'pdf, html, mp4, xlsx, docx, etc.',
    document_class  VARCHAR(100)    NOT NULL COMMENT 'meeting_agenda, meeting_minutes, meeting_packet, policy_manual, budget, annual_report, school_handbook, sepac_info, prr_response, des_report, correspondence, testimony, legal_filing, media_coverage, other',

    -- Source context
    source_system   VARCHAR(50)     NOT NULL COMMENT 'What scraper found this: dese, apptegy, civicengage, boarddocs, custom_html, manual',
    source_label    VARCHAR(255)    NULL COMMENT 'Human-readable source: "DESE Restraint Report 2024", "Attleboro SC Agenda Center"',
    district_code   VARCHAR(10)     NULL COMMENT 'DESE 8-digit district code if applicable',
    meeting_date    DATE            NULL COMMENT 'Date of meeting this document belongs to',

    -- File tracking
    file_path       VARCHAR(1024)   NULL COMMENT 'Local path after download',
    file_size       BIGINT UNSIGNED NULL COMMENT 'Bytes',
    page_count      INT UNSIGNED    NULL COMMENT 'Number of pages (PDFs only)',
    ftp_path        VARCHAR(1024)   NULL COMMENT 'Path on FTP server after upload',
    ftp_uploaded_at DATETIME        NULL,

    -- Lifecycle
    status          VARCHAR(30)     NOT NULL DEFAULT 'discovered' COMMENT 'discovered, downloaded, verified, uploaded, failed, skipped_duplicate',
    scrape_date     DATE            NOT NULL COMMENT 'Date this document was discovered/scraped',
    last_checked    DATETIME        NULL COMMENT 'Last time we verified the URL still works',
    error_message   TEXT            NULL,

    -- Strategy
    scrape_method   VARCHAR(100)    NULL COMMENT 'How we got it: direct_download, selenium_click, api_call, manual',
    scrape_notes    TEXT            NULL COMMENT 'Any notes about the scraping process for strategy learning',

    -- Timestamps
    created_at      DATETIME        NOT NULL DEFAULT NOW(),
    updated_at      DATETIME        NOT NULL DEFAULT NOW() ON UPDATE NOW(),

    -- Indexes
    UNIQUE KEY uq_source_url (source_url(768)),
    INDEX idx_media_type (media_type),
    INDEX idx_document_class (document_class),
    INDEX idx_source_system (source_system),
    INDEX idx_district_code (district_code),
    INDEX idx_meeting_date (meeting_date),
    INDEX idx_status (status),
    INDEX idx_scrape_date (scrape_date),
    INDEX idx_checksum (checksum),

    -- Foreign keys
    CONSTRAINT fk_documents_district FOREIGN KEY (district_code) REFERENCES districts(district_code) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Source Systems Registry
-- Tracks known scraping sources and their capabilities
-- ============================================================

CREATE TABLE source_systems (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    system_name     VARCHAR(50)     NOT NULL UNIQUE COMMENT 'dese, apptegy, civicengage, etc.',
    display_name    VARCHAR(255)    NOT NULL,
    base_url        VARCHAR(1024)   NULL,
    platform_type   VARCHAR(50)     NOT NULL COMMENT 'government_portal, meeting_platform, cms, cdn, bulk_export',
    auth_required   TINYINT(1)      NOT NULL DEFAULT 0,
    rate_limit      VARCHAR(50)     NULL COMMENT 'e.g. "2 req/sec", "5 min delay"',
    scraper_module  VARCHAR(255)    NULL COMMENT 'Python module path for the scraper',
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    last_scraped    DATETIME        NULL,
    notes           TEXT            NULL,
    created_at      DATETIME        NOT NULL DEFAULT NOW(),
    updated_at      DATETIME        NOT NULL DEFAULT NOW() ON UPDATE NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Seed known source systems
INSERT INTO source_systems (system_name, display_name, platform_type, scraper_module) VALUES
('dese', 'MA DESE Profiles', 'government_portal', 'scraper.scrapers.dese_all'),
('apptegy', 'Apptegy / Thrillshare', 'meeting_platform', 'scraper.scrapers.apptegy_meetings'),
('civicengage', 'CivicEngage Agenda Center', 'meeting_platform', 'scraper.scrapers.civicengage_meetings'),
('boarddocs', 'BoardDocs', 'meeting_platform', 'scraper.scrapers.boarddocs_meetings'),
('youtube', 'YouTube (district channel)', 'video_platform', 'scraper.scrapers.youtube_meetings'),
('manual', 'Manual entry', 'manual', NULL);

-- ============================================================
-- Strategy Store
-- Learned scraping patterns for re-use
-- ============================================================

CREATE TABLE scrape_strategies (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    strategy_name   VARCHAR(255)    NOT NULL,
    platform_type   VARCHAR(50)     NOT NULL,
    pattern_type    VARCHAR(50)     NOT NULL COMMENT 'url_pattern, dom_selector, api_endpoint, navigation_flow, auth_method',
    pattern_value   TEXT            NOT NULL COMMENT 'The actual pattern/selector/URL template',
    success_count   INT UNSIGNED    NOT NULL DEFAULT 0,
    fail_count      INT UNSIGNED    NOT NULL DEFAULT 0,
    last_used       DATETIME        NULL,
    last_success    DATETIME        NULL,
    example_urls    TEXT            NULL COMMENT 'JSON array of URLs where this worked',
    notes           TEXT            NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT NOW(),
    updated_at      DATETIME        NOT NULL DEFAULT NOW() ON UPDATE NOW(),
    INDEX idx_platform_type (platform_type),
    INDEX idx_pattern_type (pattern_type),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
