ALTER TABLE ordres_reparation
    ALTER COLUMN date_fin_prevue TYPE DATE
    USING date_fin_prevue::date;





CREATE TABLE ordres_reparation (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    numero                VARCHAR(25) UNIQUE,
    reception_id          UUID NOT NULL UNIQUE
        REFERENCES receptions(id) ON DELETE RESTRICT,
    vehicule_id           UUID NOT NULL
        REFERENCES vehicules(id) ON DELETE RESTRICT,

    statut                VARCHAR(15) NOT NULL DEFAULT 'OUVERT',
    urgence               VARCHAR(10) NOT NULL DEFAULT 'NORMAL',
    description_travaux   TEXT NOT NULL DEFAULT '',

    date_fin_prevue       DATE,
    duree_fin_prevu       INTEGER,
    duree_fin_reel        INTEGER,

    date_creation         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    date_cloture          TIMESTAMPTZ,

    created_by_id         UUID
        REFERENCES accounts_users(id) ON DELETE SET NULL
);

CREATE TABLE ordres_reparation_ateliers (
    id                  BIGSERIAL PRIMARY KEY,
    ordrereparation_id   UUID NOT NULL
        REFERENCES ordres_reparation(id) ON DELETE CASCADE,
    atelier_id          UUID NOT NULL
        REFERENCES ateliers(id) ON DELETE CASCADE,
    UNIQUE (ordrereparation_id, atelier_id)
);

CREATE INDEX ordres_reparation_vehicule_idx ON ordres_reparation (vehicule_id);
CREATE INDEX ordres_reparation_statut_idx ON ordres_reparation (statut);
CREATE INDEX ordres_reparation_ateliers_or_idx ON ordres_reparation_ateliers (ordrereparation_id);
CREATE INDEX ordres_reparation_ateliers_atelier_idx ON ordres_reparation_ateliers (atelier_id);





CREATE TABLE IF NOT EXISTS receptions (
    -- ── Clé primaire ──
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── Numéro unique ──
    numero            VARCHAR(20) NOT NULL UNIQUE,

    -- ── Liaisons ──
    entree_id         UUID NOT NULL UNIQUE
                      REFERENCES enregistrements_entree(id) ON DELETE RESTRICT,
    vehicule_id       UUID NOT NULL
                      REFERENCES vehicules(id) ON DELETE RESTRICT,
    receptionniste_id UUID
                      REFERENCES accounts_users(id) ON DELETE SET NULL,

    -- ── Statut ──
    statut            VARCHAR(25) NOT NULL DEFAULT 'EN_COURS',

    -- ── Contenu ──
    observations      TEXT NOT NULL DEFAULT '',

    -- ── Dates ──
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    close_at          TIMESTAMPTZ,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ── Contrainte sur le statut ──
    CONSTRAINT receptions_statut_check
        CHECK (statut IN (
            'EN_COURS',
            'RAPPORT_FAIT',
            'PRESENT_ATELIER',
            'FICHE_TECHNIQUE',
            'REPARATION_EN_COURS',
            'TRAVAUX_TERMINES',
            'BON_SORTIE_FAIT',
            'SORTI'
        ))
);

-- ── Index ──
CREATE INDEX IF NOT EXISTS idx_receptions_entree          ON receptions(entree_id);
CREATE INDEX IF NOT EXISTS idx_receptions_vehicule        ON receptions(vehicule_id);
CREATE INDEX IF NOT EXISTS idx_receptions_receptionniste  ON receptions(receptionniste_id);
CREATE INDEX IF NOT EXISTS idx_receptions_statut          ON receptions(statut);
CREATE INDEX IF NOT EXISTS idx_receptions_created_at      ON receptions(created_at DESC);











-- 1) Ajouter les colonnes manquantes
ALTER TABLE ateliers
    ADD COLUMN IF NOT EXISTS localisation   VARCHAR(150) DEFAULT '',
    ADD COLUMN IF NOT EXISTS telephone      VARCHAR(20)  DEFAULT '',
    ADD COLUMN IF NOT EXISTS specialite     VARCHAR(100) DEFAULT '',
    ADD COLUMN IF NOT EXISTS description    TEXT         DEFAULT '',
    ADD COLUMN IF NOT EXISTS responsable_id UUID,
    ADD COLUMN IF NOT EXISTS created_by_id  UUID,
    ADD COLUMN IF NOT EXISTS is_active      BOOLEAN      DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS created_at     TIMESTAMPTZ  DEFAULT NOW();

-- 2) Remplir les NULL
UPDATE ateliers SET localisation = COALESCE(localisation, '');
UPDATE ateliers SET telephone    = COALESCE(telephone, '');
UPDATE ateliers SET specialite   = COALESCE(specialite, '');
UPDATE ateliers SET description  = COALESCE(description, '');
UPDATE ateliers SET nom          = COALESCE(nom, 'Sans nom') WHERE nom IS NULL;
UPDATE ateliers SET is_active    = COALESCE(is_active, TRUE);
UPDATE ateliers SET created_at   = COALESCE(created_at, NOW());

-- 3) Contraintes NOT NULL + types
ALTER TABLE ateliers
    ALTER COLUMN nom          TYPE VARCHAR(100),
    ALTER COLUMN nom          SET NOT NULL,

    ALTER COLUMN localisation TYPE VARCHAR(150),
    ALTER COLUMN localisation SET DEFAULT '',
    ALTER COLUMN localisation SET NOT NULL,

    ALTER COLUMN telephone    TYPE VARCHAR(20),
    ALTER COLUMN telephone    SET DEFAULT '',
    ALTER COLUMN telephone    SET NOT NULL,

    ALTER COLUMN specialite   TYPE VARCHAR(100),
    ALTER COLUMN specialite   SET DEFAULT '',
    ALTER COLUMN specialite   SET NOT NULL,

    ALTER COLUMN description  TYPE TEXT,
    ALTER COLUMN description  SET DEFAULT '',
    ALTER COLUMN description  SET NOT NULL,

    ALTER COLUMN is_active    SET DEFAULT TRUE,
    ALTER COLUMN is_active    SET NOT NULL,

    ALTER COLUMN created_at   TYPE TIMESTAMPTZ,
    ALTER COLUMN created_at   SET DEFAULT NOW(),
    ALTER COLUMN created_at   SET NOT NULL;



-- ── Index ──
CREATE INDEX idx_ateliers_responsable ON ateliers(responsable_id);
CREATE INDEX idx_ateliers_created_by  ON ateliers(created_by_id);
CREATE INDEX idx_ateliers_is_active   ON ateliers(is_active);
CREATE INDEX idx_ateliers_nom         ON ateliers(nom);



CREATE TABLE ordres_reparation_ateliers (
    id                 BIGSERIAL PRIMARY KEY,
    ordrereparation_id UUID NOT NULL
                       REFERENCES ordres_reparation(id) ON DELETE CASCADE,
    atelier_id         UUID NOT NULL
                       REFERENCES ateliers(id) ON DELETE CASCADE,
    CONSTRAINT ordres_reparation_ateliers_unique
        UNIQUE (ordrereparation_id, atelier_id)
);

CREATE INDEX idx_ora_ordre   ON ordres_reparation_ateliers(ordrereparation_id);
CREATE INDEX idx_ora_atelier ON ordres_reparation_ateliers(atelier_id);


-- Fiche technique
ALTER TABLE fiches_techniques
    ALTER COLUMN rendre_pieces   TYPE VARCHAR(3) USING (CASE WHEN rendre_pieces THEN 'OUI' ELSE 'NON' END),
    ALTER COLUMN ecrou_antivol   TYPE VARCHAR(3) USING (CASE WHEN ecrou_antivol THEN 'OUI' ELSE 'NON' END),
    ALTER COLUMN alarme          TYPE VARCHAR(3) USING (CASE WHEN alarme THEN 'OUI' ELSE 'NON' END);

-- Ajouter un défaut si besoin
ALTER TABLE fiches_techniques
    ALTER COLUMN rendre_pieces   SET DEFAULT '',
    ALTER COLUMN ecrou_antivol   SET DEFAULT '',
    ALTER COLUMN alarme          SET DEFAULT '';







CREATE TABLE IF NOT EXISTS taches_atelier_techniciens (
    id         BIGSERIAL PRIMARY KEY,
    tache_id   UUID NOT NULL REFERENCES taches_atelier(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES accounts_users(id) ON DELETE CASCADE,
    CONSTRAINT taches_atelier_techniciens_unique UNIQUE (tache_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_tat_tache ON taches_atelier_techniciens(tache_id);
CREATE INDEX IF NOT EXISTS idx_tat_user  ON taches_atelier_techniciens(user_id);



CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE taches_atelier (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    ordre_reparation_id     UUID NOT NULL
        REFERENCES ordres_reparation(id) ON DELETE CASCADE,

    atelier_id              UUID NOT NULL
        REFERENCES ateliers(id) ON DELETE RESTRICT,

    libelle                 VARCHAR(200) NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    priorite                VARCHAR(10) NOT NULL DEFAULT 'NORMALE',
    statut                  VARCHAR(10) NOT NULL DEFAULT 'A_FAIRE',

    duree_estimee_minutes   INTEGER NOT NULL DEFAULT 60,
    duree_reelle_minutes    INTEGER,

    date_assignation        TIMESTAMPTZ,
    date_debut              TIMESTAMPTZ,
    date_fin                TIMESTAMPTZ,
    date_validation         TIMESTAMPTZ,

    valide_par_id           UUID
        REFERENCES accounts_users(id) ON DELETE SET NULL,

    commentaire_validation  TEXT NOT NULL DEFAULT '',
    signature_chef          TEXT NOT NULL DEFAULT '',
    cloturee_manuellement   BOOLEAN NOT NULL DEFAULT FALSE,

    created_by_id           UUID
        REFERENCES accounts_users(id) ON DELETE SET NULL,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE taches_techniciens (
    id          BIGSERIAL PRIMARY KEY,
    tache_id    UUID NOT NULL
        REFERENCES taches_atelier(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL
        REFERENCES accounts_users(id) ON DELETE CASCADE,
    UNIQUE (tache_id, user_id)
);

CREATE INDEX taches_or_idx ON taches_atelier (ordre_reparation_id);
CREATE INDEX taches_atelier_idx ON taches_atelier (atelier_id);
CREATE INDEX taches_techniciens_tache_idx ON taches_techniciens (tache_id);
CREATE INDEX taches_techniciens_user_idx ON taches_techniciens (user_id);




CREATE TABLE IF NOT EXISTS comptes_rendus_taches (
    -- ── Clé primaire ──
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── Liaisons ──
    tache_id        UUID NOT NULL
                    REFERENCES taches_atelier(id) ON DELETE CASCADE,
    technicien_id   UUID
                    REFERENCES accounts_users(id) ON DELETE SET NULL,

    -- ── Contenu ──
    description     TEXT    NOT NULL DEFAULT '',
    pieces_utilisees TEXT   NOT NULL DEFAULT '',
    observations    TEXT    NOT NULL DEFAULT '',
    duree_minutes   INTEGER NOT NULL DEFAULT 0,

    -- ── Métadonnées ──
    saisie_par_chef BOOLEAN NOT NULL DEFAULT FALSE,
    date_saisie     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ── Contraintes ──
    CONSTRAINT comptes_rendus_duree_check
        CHECK (duree_minutes >= 0)
);

-- ── Index ──
CREATE INDEX IF NOT EXISTS idx_crt_tache       ON comptes_rendus_taches(tache_id);
CREATE INDEX IF NOT EXISTS idx_crt_technicien  ON comptes_rendus_taches(technicien_id);
CREATE INDEX IF NOT EXISTS idx_crt_date        ON comptes_rendus_taches(date_saisie DESC);








CREATE TABLE IF NOT EXISTS inv_inventaire (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    date                DATE NOT NULL DEFAULT CURRENT_DATE,
    statut              VARCHAR(10) NOT NULL DEFAULT 'EN_COURS',

    cree_par_id         UUID REFERENCES accounts_users(id) ON DELETE SET NULL,
    date_creation       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    soumis_par_id       UUID REFERENCES accounts_users(id) ON DELETE SET NULL,
    date_soumission     TIMESTAMPTZ,
    observation         TEXT NOT NULL DEFAULT '',

    decide_par_id       UUID REFERENCES accounts_users(id) ON DELETE SET NULL,
    date_decision       TIMESTAMPTZ,
    motif_revocation    TEXT NOT NULL DEFAULT '',

    rapport             JSONB NOT NULL DEFAULT '{}'::jsonb,

    email_envoye        BOOLEAN NOT NULL DEFAULT FALSE,
    email_erreur        TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_inv_inventaire_statut    ON inv_inventaire(statut);
CREATE INDEX IF NOT EXISTS idx_inv_inventaire_date      ON inv_inventaire(date DESC);
CREATE INDEX IF NOT EXISTS idx_inv_inventaire_creation  ON inv_inventaire(date_creation DESC);




CREATE TABLE IF NOT EXISTS inv_ligne (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    inventaire_id     UUID NOT NULL
                      REFERENCES inv_inventaire(id) ON DELETE CASCADE,
    vehicule_id       UUID NOT NULL
                      REFERENCES vehicules(id) ON DELETE CASCADE,
    entree_id         UUID
                      REFERENCES enregistrements_entree(id) ON DELETE SET NULL,

    presence          VARCHAR(10) NOT NULL DEFAULT 'A_VERIFIER',

    verifie_par_id    UUID REFERENCES accounts_users(id) ON DELETE SET NULL,
    date_verification TIMESTAMPTZ,

    CONSTRAINT uniq_inv_ligne_vehicule
        UNIQUE (inventaire_id, vehicule_id)
);

CREATE INDEX IF NOT EXISTS idx_inv_ligne_inventaire ON inv_ligne(inventaire_id);
CREATE INDEX IF NOT EXISTS idx_inv_ligne_vehicule   ON inv_ligne(vehicule_id);
CREATE INDEX IF NOT EXISTS idx_inv_ligne_presence   ON inv_ligne(presence);



CREATE TABLE IF NOT EXISTS inv_mouvement_temp (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    inventaire_id     UUID NOT NULL
                      REFERENCES inv_inventaire(id) ON DELETE CASCADE,
    type              VARCHAR(6) NOT NULL,

    vehicule_id       UUID NOT NULL
                      REFERENCES vehiculese(id) ON DELETE CASCADE,

    matricule         VARCHAR(30)  NOT NULL DEFAULT '',
    chauffeur         VARCHAR(120) NOT NULL DEFAULT '',
    chauffeur_tel     VARCHAR(30)  NOT NULL DEFAULT '',

    conducteur_id     UUID REFERENCES conducteurs(id) ON DELETE SET NULL,

    motif             VARCHAR(30)  NOT NULL DEFAULT '',

    entree_id         UUID REFERENCES enregistrements_entree(id) ON DELETE SET NULL,

    cree_par_id       UUID REFERENCES accounts_users(id) ON DELETE SET NULL,
    date_creation     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    erreur            TEXT NOT NULL DEFAULT '',

    CONSTRAINT uniq_inv_mouvement_vehicule
        UNIQUE (inventaire_id, vehicule_id)
);

CREATE INDEX IF NOT EXISTS idx_inv_mvt_inventaire ON inv_mouvement_temp(inventaire_id);
CREATE INDEX IF NOT EXISTS idx_inv_mvt_vehicule   ON inv_mouvement_temp(vehicule_id);
CREATE INDEX IF NOT EXISTS idx_inv_mvt_type       ON inv_mouvement_temp(type);



CREATE TABLE IF NOT EXISTS reouvertures_or (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    ordre_reparation_id   UUID NOT NULL
                          REFERENCES ordres_reparation(id) ON DELETE CASCADE,

    duree_prevue_minutes  INTEGER NOT NULL DEFAULT 0
                          CHECK (duree_prevue_minutes >= 0),

    raison                TEXT NOT NULL DEFAULT '',

    reouvert_par_id       UUID
                          REFERENCES accounts_users(id) ON DELETE SET NULL,

    date_reouverture      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reo_or            ON reouvertures_or(ordre_reparation_id);
CREATE INDEX IF NOT EXISTS idx_reo_user          ON reouvertures_or(reouvert_par_id);
CREATE INDEX IF NOT EXISTS idx_reo_date          ON reouvertures_or(date_reouverture DESC);


CREATE TABLE IF NOT EXISTS reouvertures_or_taches (
    id                BIGSERIAL PRIMARY KEY,

    reouvertureor_id  UUID NOT NULL
                      REFERENCES reouvertures_or(id) ON DELETE CASCADE,

    tache_id          UUID NOT NULL
                      REFERENCES taches_atelier(id) ON DELETE CASCADE,

    CONSTRAINT reouvertures_or_taches_unique
        UNIQUE (reouvertureor_id, tache_id)
);

CREATE INDEX IF NOT EXISTS idx_reo_taches_reo    ON reouvertures_or_taches(reouvertureor_id);
CREATE INDEX IF NOT EXISTS idx_reo_taches_tache  ON reouvertures_or_taches(tache_id);


ALTER TABLE IF EXISTS public.clients
    ADD COLUMN IF NOT EXISTS parent_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'clients_parent_id_fk'
    ) THEN
        ALTER TABLE public.clients
            ADD CONSTRAINT clients_parent_id_fk
            FOREIGN KEY (parent_id)
            REFERENCES public.clients(id)
            ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_clients_parent_id ON public.clients(parent_id);


ALTER TABLE taches_atelier
    ADD COLUMN IF NOT EXISTS type_retour     VARCHAR(12) NOT NULL DEFAULT 'AUCUN',
    ADD COLUMN IF NOT EXISTS motif_retour    TEXT        NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS date_retour     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS nb_refus        INTEGER     NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS nb_reouvertures INTEGER     NOT NULL DEFAULT 0;




-- 1) Ajouter la colonne (nullable)
ALTER TABLE reouvertures_or
    ADD COLUMN IF NOT EXISTS reception_id UUID;

-- 2) Ajouter la contrainte FK
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'reouvertures_or_reception_fk'
    ) THEN
        ALTER TABLE reouvertures_or
            ADD CONSTRAINT reouvertures_or_reception_fk
            FOREIGN KEY (reception_id)
            REFERENCES receptions(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- 3) Index pour accélérer reception.reouvertures_or.all()
CREATE INDEX IF NOT EXISTS idx_reo_reception
    ON reouvertures_or(reception_id);















