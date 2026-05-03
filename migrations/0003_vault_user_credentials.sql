ALTER TABLE user_credentials
    RENAME COLUMN openbao_path TO vault_secret_name;
