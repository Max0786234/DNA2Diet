-- DNA2Diet Database Schema
-- MySQL Database Setup

CREATE DATABASE IF NOT EXISTS dna2diet;
USE dna2diet;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email (email)
);

-- User profiles table (demographic and health data)
CREATE TABLE IF NOT EXISTS user_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    age INT,
    gender ENUM('male', 'female', 'other', 'prefer_not_to_say'),
    height DECIMAL(5,2) COMMENT 'Height in cm',
    weight DECIMAL(5,2) COMMENT 'Weight in kg',
    bmi DECIMAL(4,2) COMMENT 'Body Mass Index',
    blood_type VARCHAR(10),
    activity_level ENUM('sedentary', 'lightly_active', 'moderately_active', 'very_active', 'extremely_active'),
    medical_history TEXT,
    allergies TEXT,
    medications TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_profile (user_id)
);

-- Analyses table (tracks each genome analysis)
CREATE TABLE IF NOT EXISTS analyses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    genome_filename VARCHAR(255) NOT NULL,
    filepath VARCHAR(500) NOT NULL,
    status ENUM('processing', 'completed', 'failed') DEFAULT 'processing',
    error_message TEXT,
    nutritional_snp_path VARCHAR(500),
    disease_candidates_path VARCHAR(500),
    selected_diseases_path VARCHAR(500),
    disease_json_path VARCHAR(500),
    ingredient_json_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_status (user_id, status),
    INDEX idx_created (created_at)
);

