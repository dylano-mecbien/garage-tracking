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


CREATE TABLE IF NOT EXISTS fiches_techniques (
    -- ── Clé primaire + liaison ──
    id                                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_fiche                        VARCHAR(20)  NOT NULL DEFAULT '',
    entree_id                           UUID         NOT NULL UNIQUE
                                        REFERENCES enregistrements_entree(id) ON DELETE RESTRICT,

    -- ── En-tête ──
    entree_le                           DATE,
    sortie_le                           DATE,
    nom_client                          VARCHAR(100) NOT NULL DEFAULT '',
    immatriculation                     VARCHAR(20)  NOT NULL DEFAULT '',
    vehicule                            VARCHAR(100) NOT NULL DEFAULT '',
    kilometrage                         INTEGER      NOT NULL DEFAULT 0,
    preconisation_courroie_distribution DATE,
    rendre_pieces                       VARCHAR(3)   NOT NULL DEFAULT '',
    ecrou_antivol                       VARCHAR(3)   NOT NULL DEFAULT '',
    alarme                              VARCHAR(3)   NOT NULL DEFAULT '',

    -- ── Véhicule au sol ──
    eclairage_av_veilleuses             VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_av_croisement             VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_av_route                  VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_av_antibrouillard         VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_av_clignotants            VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_ar_feux_position          VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_ar_stop                   VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_ar_clignotants            VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_ar_recul                  VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_ar_antibrouillard         VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_ar_feu_plaque             VARCHAR(10) NOT NULL DEFAULT '',
    eclairage_ar_3eme_feu_stop          VARCHAR(10) NOT NULL DEFAULT '',
    controle_hauteur_phare              VARCHAR(10) NOT NULL DEFAULT '',
    voyant_tableau_bord                 VARCHAR(10) NOT NULL DEFAULT '',
    code_defaut                         VARCHAR(10) NOT NULL DEFAULT '',
    bougies_faisceau                    VARCHAR(10) NOT NULL DEFAULT '',
    sonde_lamda                         VARCHAR(10) NOT NULL DEFAULT '',
    course_pedale_frein                 VARCHAR(10) NOT NULL DEFAULT '',
    course_frein_main                   VARCHAR(10) NOT NULL DEFAULT '',
    liquide_frein_temperature           NUMERIC(5,1),
    liquide_frein_etat                  VARCHAR(10) NOT NULL DEFAULT '',
    maitre_cylindre_fuite               VARCHAR(10) NOT NULL DEFAULT '',
    climatisation_temperature_soufflage NUMERIC(5,1),
    climatisation_filtre_habitacle      VARCHAR(10) NOT NULL DEFAULT '',
    niveau_huile_prise_en_charge        VARCHAR(10) NOT NULL DEFAULT '',
    balais_essuie_glace_av              VARCHAR(10) NOT NULL DEFAULT '',
    balais_essuie_glace_ar              VARCHAR(10) NOT NULL DEFAULT '',
    pare_brise_impact                   VARCHAR(3)  NOT NULL DEFAULT '',
    pare_brise_fissure                  VARCHAR(3)  NOT NULL DEFAULT '',
    pare_brise_fissure_appeler_le       VARCHAR(20) NOT NULL DEFAULT '',
    jauge_carburant                     VARCHAR(15) NOT NULL DEFAULT '',
    plaques_immatriculation_av          VARCHAR(10) NOT NULL DEFAULT '',
    plaques_immatriculation_ar          VARCHAR(10) NOT NULL DEFAULT '',
    batterie                            VARCHAR(10) NOT NULL DEFAULT '',
    alternateur_demarreur               VARCHAR(10) NOT NULL DEFAULT '',
    liquide_refroidissement             VARCHAR(10) NOT NULL DEFAULT '',

    -- ── Véhicule mi-hauteur ──
    pneu_av_g_profondeur                NUMERIC(4,1),
    pneu_av_d_profondeur                NUMERIC(4,1),
    pneu_ar_g_profondeur                NUMERIC(4,1),
    pneu_ar_d_profondeur                NUMERIC(4,1),
    pneu_roue_secours_profondeur        NUMERIC(4,1),
    pneu_av_g_usure                     VARCHAR(10) NOT NULL DEFAULT '',
    pneu_av_d_usure                     VARCHAR(10) NOT NULL DEFAULT '',
    pneu_ar_g_usure                     VARCHAR(10) NOT NULL DEFAULT '',
    pneu_ar_d_usure                     VARCHAR(10) NOT NULL DEFAULT '',
    geometrie_necessaire                VARCHAR(3)  NOT NULL DEFAULT '',

    susp_amortisseurs_av_g              VARCHAR(10) NOT NULL DEFAULT '',
    susp_amortisseurs_av_d              VARCHAR(10) NOT NULL DEFAULT '',
    susp_amortisseurs_ar_g              VARCHAR(10) NOT NULL DEFAULT '',
    susp_amortisseurs_ar_d              VARCHAR(10) NOT NULL DEFAULT '',
    susp_coupelles_av_g                 VARCHAR(10) NOT NULL DEFAULT '',
    susp_coupelles_av_d                 VARCHAR(10) NOT NULL DEFAULT '',
    susp_coupelles_ar_g                 VARCHAR(10) NOT NULL DEFAULT '',
    susp_coupelles_ar_d                 VARCHAR(10) NOT NULL DEFAULT '',
    susp_ressorts_av_g                  VARCHAR(10) NOT NULL DEFAULT '',
    susp_ressorts_av_d                  VARCHAR(10) NOT NULL DEFAULT '',
    susp_ressorts_ar_g                  VARCHAR(10) NOT NULL DEFAULT '',
    susp_ressorts_ar_d                  VARCHAR(10) NOT NULL DEFAULT '',
    susp_kit_protection_av_g            VARCHAR(10) NOT NULL DEFAULT '',
    susp_kit_protection_av_d            VARCHAR(10) NOT NULL DEFAULT '',
    susp_kit_protection_ar_g            VARCHAR(10) NOT NULL DEFAULT '',
    susp_kit_protection_ar_d            VARCHAR(10) NOT NULL DEFAULT '',
    susp_butees_av_g                    VARCHAR(10) NOT NULL DEFAULT '',
    susp_butees_av_d                    VARCHAR(10) NOT NULL DEFAULT '',
    susp_butees_ar_g                    VARCHAR(10) NOT NULL DEFAULT '',
    susp_butees_ar_d                    VARCHAR(10) NOT NULL DEFAULT '',
    susp_biellettes_av_g                VARCHAR(10) NOT NULL DEFAULT '',
    susp_biellettes_av_d                VARCHAR(10) NOT NULL DEFAULT '',
    susp_biellettes_ar_g                VARCHAR(10) NOT NULL DEFAULT '',
    susp_biellettes_ar_d                VARCHAR(10) NOT NULL DEFAULT '',

    frein_flexibles_av_g                VARCHAR(10) NOT NULL DEFAULT '',
    frein_flexibles_av_d                VARCHAR(10) NOT NULL DEFAULT '',
    frein_flexibles_ar_g                VARCHAR(10) NOT NULL DEFAULT '',
    frein_flexibles_ar_d                VARCHAR(10) NOT NULL DEFAULT '',
    frein_disques_av_g                  VARCHAR(10) NOT NULL DEFAULT '',
    frein_disques_av_d                  VARCHAR(10) NOT NULL DEFAULT '',
    frein_disques_ar_g                  VARCHAR(10) NOT NULL DEFAULT '',
    frein_disques_ar_d                  VARCHAR(10) NOT NULL DEFAULT '',
    frein_disques_epaisseur_mm          NUMERIC(4,1),
    frein_plaquettes_av_g               VARCHAR(10) NOT NULL DEFAULT '',
    frein_plaquettes_av_d               VARCHAR(10) NOT NULL DEFAULT '',
    frein_plaquettes_ar_g               VARCHAR(10) NOT NULL DEFAULT '',
    frein_plaquettes_ar_d               VARCHAR(10) NOT NULL DEFAULT '',
    frein_kit_frein_ar_g                VARCHAR(10) NOT NULL DEFAULT '',
    frein_kit_frein_ar_d                VARCHAR(10) NOT NULL DEFAULT '',
    frein_tambours_ar_g                 VARCHAR(10) NOT NULL DEFAULT '',
    frein_tambours_ar_d                 VARCHAR(10) NOT NULL DEFAULT '',
    frein_tambours_diametre_mm          NUMERIC(4,1),

    train_flexibles_av_g                VARCHAR(10) NOT NULL DEFAULT '',
    train_flexibles_av_d                VARCHAR(10) NOT NULL DEFAULT '',
    train_flexibles_ar_g                VARCHAR(10) NOT NULL DEFAULT '',
    train_flexibles_ar_d                VARCHAR(10) NOT NULL DEFAULT '',
    train_disques_av_g                  VARCHAR(10) NOT NULL DEFAULT '',
    train_disques_av_d                  VARCHAR(10) NOT NULL DEFAULT '',
    train_disques_ar_g                  VARCHAR(10) NOT NULL DEFAULT '',
    train_disques_ar_d                  VARCHAR(10) NOT NULL DEFAULT '',
    train_plaquettes_av_g               VARCHAR(10) NOT NULL DEFAULT '',
    train_plaquettes_av_d               VARCHAR(10) NOT NULL DEFAULT '',
    train_plaquettes_ar_g               VARCHAR(10) NOT NULL DEFAULT '',
    train_plaquettes_ar_d               VARCHAR(10) NOT NULL DEFAULT '',
    train_kit_frein_av_g                VARCHAR(10) NOT NULL DEFAULT '',
    train_kit_frein_av_d                VARCHAR(10) NOT NULL DEFAULT '',
    train_tambours_av_g                 VARCHAR(10) NOT NULL DEFAULT '',
    train_tambours_av_d                 VARCHAR(10) NOT NULL DEFAULT '',
    train_tambours_ar_g                 VARCHAR(10) NOT NULL DEFAULT '',
    train_tambours_ar_d                 VARCHAR(10) NOT NULL DEFAULT '',

    -- ── Véhicule levé ──
    echap_catalyseur_filtre_particules  VARCHAR(10) NOT NULL DEFAULT '',
    echap_partie_avant                  VARCHAR(10) NOT NULL DEFAULT '',
    echap_partie_intermediaire          VARCHAR(10) NOT NULL DEFAULT '',
    echap_partie_arriere                VARCHAR(10) NOT NULL DEFAULT '',
    echap_fixations                     VARCHAR(10) NOT NULL DEFAULT '',
    transmission_soufflets_g            VARCHAR(10) NOT NULL DEFAULT '',
    transmission_soufflets_d            VARCHAR(10) NOT NULL DEFAULT '',
    transmission_cardans_g              VARCHAR(10) NOT NULL DEFAULT '',
    transmission_cardans_d              VARCHAR(10) NOT NULL DEFAULT '',
    frein_canalisation                  VARCHAR(10) NOT NULL DEFAULT '',
    frein_cable_frein_main              VARCHAR(10) NOT NULL DEFAULT '',
    frein_repartiteur_fuite             VARCHAR(10) NOT NULL DEFAULT '',
    fuite_moteur                        VARCHAR(3)  NOT NULL DEFAULT '',

    -- ── Post-contrôles ──
    niveau_huile_apres_intervention     VARCHAR(10) NOT NULL DEFAULT '',
    ok_lave_glace                       BOOLEAN NOT NULL DEFAULT FALSE,
    ok_liquide_refroidissement          BOOLEAN NOT NULL DEFAULT FALSE,
    ok_kit_securite                     BOOLEAN NOT NULL DEFAULT FALSE,
    ok_boite_ampoules                   BOOLEAN NOT NULL DEFAULT FALSE,
    ok_etiquette_vidange                BOOLEAN NOT NULL DEFAULT FALSE,
    ok_etiquette_monte_pneumatique      BOOLEAN NOT NULL DEFAULT FALSE,
    ok_remise_a_zero_maintenance        BOOLEAN NOT NULL DEFAULT FALSE,

    -- ── Diagnostic & synthèse ──
    diagnostic                          TEXT          NOT NULL DEFAULT '',
    pieces_recommandees                 TEXT          NOT NULL DEFAULT '',
    main_oeuvre_estimee                 NUMERIC(10,2) NOT NULL DEFAULT 0,
    pieces_estimees                     NUMERIC(10,2) NOT NULL DEFAULT 0,
    temps_estime_heures                 NUMERIC(6,2)  NOT NULL DEFAULT 0,
    commentaires                        TEXT          NOT NULL DEFAULT '',
    observations                        TEXT          NOT NULL DEFAULT '',

    -- ── Signatures ──
    nom_controleur                      VARCHAR(100) NOT NULL DEFAULT '',
    signature_controleur                TEXT         NOT NULL DEFAULT '',
    nom_client_signataire               VARCHAR(100) NOT NULL DEFAULT '',
    signature_client                    TEXT         NOT NULL DEFAULT '',

    -- ── Meta ──
    cree_par_id                         UUID REFERENCES accounts_users(id) ON DELETE SET NULL,
    date_creation                       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── Index ──
CREATE INDEX IF NOT EXISTS idx_ft_entree    ON fiches_techniques(entree_id);
CREATE INDEX IF NOT EXISTS idx_ft_cree_par  ON fiches_techniques(cree_par_id);
CREATE INDEX IF NOT EXISTS idx_ft_date      ON fiches_techniques(date_creation DESC);
CREATE INDEX IF NOT EXISTS idx_ft_immat     ON fiches_techniques(immatriculation);

CREATE INDEX idx_fiches_techniques_entre       ON fiches_techniques(entree_id);
CREATE INDEX idx_fiches_techniques_date        ON fiches_techniques(date_creation DESC);
CREATE INDEX idx_fiches_techniques_cree_par    ON fiches_techniques(cree_par_id);





CREATE TABLE fiches_controle (
    -- ── Clé primaire & liaison ──
    id                                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entree_id                                   UUID NOT NULL UNIQUE
                                                REFERENCES enregistrements_entree(id) ON DELETE RESTRICT,

    -- ── En-tête ──
    travail_a_effectuer                         TEXT NOT NULL DEFAULT '',
    entree_le                                   DATE,
    sortir_le                                   DATE,
    immatriculation                             VARCHAR(20) NOT NULL DEFAULT '',
    marque                                      VARCHAR(50) NOT NULL DEFAULT '',
    modele                                      VARCHAR(50) NOT NULL DEFAULT '',
    kilometrage                                 INTEGER NOT NULL DEFAULT 0,
    telephone                                   VARCHAR(20) NOT NULL DEFAULT '',

    -- ── Colonne 1 ──
    alarme_fonctionne                           VARCHAR(10) NOT NULL DEFAULT '',
    verrouillage_portes                         VARCHAR(10) NOT NULL DEFAULT '',
    telecommande_ouverture                      VARCHAR(10) NOT NULL DEFAULT '',
    trappe_carburant                            VARCHAR(10) NOT NULL DEFAULT '',
    tirette_capot                               VARCHAR(10) NOT NULL DEFAULT '',
    climatisation_fonctionne                    VARCHAR(10) NOT NULL DEFAULT '',
    climatisation_fait_froid                    VARCHAR(10) NOT NULL DEFAULT '',
    voyant_moteur_tableau_bord                  BOOLEAN,
    autoradio_s_allume                          VARCHAR(10) NOT NULL DEFAULT '',
    son_dans_baffles                            VARCHAR(10) NOT NULL DEFAULT '',
    dossier_vehicule_complet                    BOOLEAN,
    horloge_a_heure                             VARCHAR(10) NOT NULL DEFAULT '',

    triangles_securite_presents                 BOOLEAN,
    triangles_securite_nombre                   SMALLINT CHECK (triangles_securite_nombre IS NULL OR triangles_securite_nombre >= 0),
    cales_metalliques_presentes                 BOOLEAN,
    cales_metalliques_nombre                    SMALLINT CHECK (cales_metalliques_nombre IS NULL OR cales_metalliques_nombre >= 0),

    gilet_securite_present                      BOOLEAN,
    extincteur_present                          BOOLEAN,
    boite_pharmacie_presente                    BOOLEAN,
    bouton_eclairage_plafonnier                 BOOLEAN,
    roue_secours_gonflee                        BOOLEAN,

    cric_present                                BOOLEAN NOT NULL DEFAULT FALSE,
    manivelle_presente                          BOOLEAN NOT NULL DEFAULT FALSE,
    cle_roue_presente                           BOOLEAN NOT NULL DEFAULT FALSE,

    joints_portieres_propres                    VARCHAR(10) NOT NULL DEFAULT '',
    enjoliveurs_roues_presents                  VARCHAR(10) NOT NULL DEFAULT '',
    plaques_immatriculation_avant_arriere       VARCHAR(10) NOT NULL DEFAULT '',
    tares_avant_arriere_presentes               VARCHAR(10) NOT NULL DEFAULT '',
    garde_boues_presents_bien_montes            VARCHAR(10) NOT NULL DEFAULT '',
    agrafes_presentes                           VARCHAR(10) NOT NULL DEFAULT '',

    -- ── Colonne 2 ──
    bavettes_et_goujons_roues_presents          BOOLEAN,
    pare_brise_etat                             VARCHAR(10) NOT NULL DEFAULT '',
    pression_pneus_bonne                        VARCHAR(10) NOT NULL DEFAULT '',
    balais_essuie_glace_avant_arriere           VARCHAR(10) NOT NULL DEFAULT '',
    gicleur_lave_glace_bocal_reserve            VARCHAR(10) NOT NULL DEFAULT '',
    miroirs_retroviseurs_etat                   VARCHAR(10) NOT NULL DEFAULT '',
    retroviseurs_se_rabattent                   VARCHAR(10) NOT NULL DEFAULT '',
    phares_avant_etat                           VARCHAR(10) NOT NULL DEFAULT '',
    camera_recul_fonctionne                     VARCHAR(10) NOT NULL DEFAULT '',
    klaxon_fonctionne                           VARCHAR(10) NOT NULL DEFAULT '',
    clignotants_avant_arriere_fonctionnent      VARCHAR(10) NOT NULL DEFAULT '',
    capteurs_position_avant_arriere_bipent      VARCHAR(10) NOT NULL DEFAULT '',
    antibrouillards_feux_jour_bon_etat          VARCHAR(10) NOT NULL DEFAULT '',
    feux_arriere_etat                           VARCHAR(10) NOT NULL DEFAULT '',
    systeme_demarrage_fonctionne                VARCHAR(10) NOT NULL DEFAULT '',
    voyant_ceintures_securite_s_allume          VARCHAR(10) NOT NULL DEFAULT '',

    -- ── Colonne 3 ──
    sieges_propres_bon_etat                     BOOLEAN,
    tapis_sol_5_presents                        BOOLEAN,
    vitres_avant_se_baissent                    BOOLEAN,
    vitres_arriere_se_baissent                  BOOLEAN,
    telecommande_vitres_fonctionne              BOOLEAN,
    autocollants_pare_brise_presents            BOOLEAN,
    voiles_peinture_sur_vitres                  BOOLEAN,

    jauge_carburant                             VARCHAR(15) NOT NULL DEFAULT '',

    -- ── Schéma carrosserie ──
    type_vehicule                               VARCHAR(20) NOT NULL DEFAULT '',
    points_degats_carrosserie                   JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- ── Synthèse ──
    etat_general                                VARCHAR(20) NOT NULL DEFAULT 'BON',
    commentaires                                TEXT NOT NULL DEFAULT '',
    defauts_observes                            TEXT NOT NULL DEFAULT '',

    -- ── Signatures ──
    nom_receptionniste                          VARCHAR(100) NOT NULL DEFAULT '',
    signature_receptionniste                    TEXT NOT NULL DEFAULT '',
    nom_client_avant                            VARCHAR(100) NOT NULL DEFAULT '',
    signature_client_avant                      TEXT NOT NULL DEFAULT '',
    nom_client_apres                            VARCHAR(100) NOT NULL DEFAULT '',
    signature_client_apres                      TEXT NOT NULL DEFAULT '',
    nom_technicien                              VARCHAR(100) NOT NULL DEFAULT '',
    signature_technicien                        TEXT NOT NULL DEFAULT '',
    nom_controleur                              VARCHAR(100) NOT NULL DEFAULT '',
    signature_controleur                        TEXT NOT NULL DEFAULT '',

    inspecte_par_id                             UUID REFERENCES accounts_users(id) ON DELETE SET NULL,
    date_inspection                             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fiches_controle_entree        ON fiches_controle(entree_id);
CREATE INDEX idx_fiches_controle_date          ON fiches_controle(date_inspection DESC);
CREATE INDEX idx_fiches_controle_inspecte_par  ON fiches_controle(inspecte_par_id);










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

