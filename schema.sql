CREATE TABLE IF NOT EXISTS check_ins (
    id             BIGSERIAL PRIMARY KEY,
    agreement_number VARCHAR(50),
    member_name    VARCHAR(255),
    checkin_datetime TIMESTAMP NOT NULL,
    gender         VARCHAR(10)
);

CREATE INDEX IF NOT EXISTS idx_checkin_datetime    ON check_ins (checkin_datetime);
CREATE INDEX IF NOT EXISTS idx_agreement_number    ON check_ins (agreement_number);
CREATE INDEX IF NOT EXISTS idx_checkin_date        ON check_ins (DATE(checkin_datetime));
