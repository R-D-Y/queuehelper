#!/bin/bash

# Définition du seuil (90%)
THRESHOLD=90

# Fichiers de sortie
PLAN_LIMITE_FILE="plan-pres-limite.txt"
ALLOCATED_TROP_FILE="alocated-trop-grand.txt"

# Nettoyage des fichiers avant d'ajouter du contenu
> "$PLAN_LIMITE_FILE"
> "$ALLOCATED_TROP_FILE"

echo "Début du script de vérification des bases de données..."

# Lire chaque abonnement depuis sub.txt
while read -r subscription; do
    echo "Traitement de l'abonnement: $subscription"
    az account set --subscription "$subscription"

    # Récupérer la liste des serveurs SQL et leurs groupes de ressources
    servers=$(az sql server list --query "[].{name:name, resourceGroup:resourceGroup}" --output json)

    # Vérifier chaque serveur SQL
    echo "$servers" | jq -c '.[]' | while read server; do
        serverName=$(echo "$server" | jq -r '.name')
        resourceGroup=$(echo "$server" | jq -r '.resourceGroup')

        echo "  -> Traitement du serveur: $serverName (Groupe de ressources: $resourceGroup)"

        # Récupérer toutes les bases de données du serveur
        databases=$(az sql db list --server "$serverName" --resource-group "$resourceGroup" --query "[].{name:name, maxSize:maxSizeBytes, allocatedSize:status.storageUsedInBytes}" --output json)

        # Vérifier chaque base de données
        echo "$databases" | jq -c '.[]' | while read db; do
            dbName=$(echo "$db" | jq -r '.name')
            maxSize=$(echo "$db" | jq -r '.maxSize')
            allocatedSize=$(echo "$db" | jq -r '.allocatedSize')

            # Vérification si les valeurs existent
            if [[ "$maxSize" == "null" || "$allocatedSize" == "null" ]]; then
                continue
            fi

            # Calcul du pourcentage d'utilisation
            usagePercentage=$(( (allocatedSize * 100) / maxSize ))

            # Vérifier si la BD est proche de la limite
            if [[ $usagePercentage -ge $THRESHOLD ]]; then
                echo "$subscription | $resourceGroup | $serverName | $dbName | Utilisation: $usagePercentage% | Plan: $(($maxSize / 1024 / 1024 / 1024)) Go | Utilisé: $(($allocatedSize / 1024 / 1024 / 1024)) Go" >> "$PLAN_LIMITE_FILE"
            fi

            # Vérifier si la BD dépasse son plan
            if [[ $allocatedSize -gt $maxSize ]]; then
                echo "$subscription | $resourceGroup | $serverName | $dbName | Plan: $(($maxSize / 1024 / 1024 / 1024)) Go | Utilisé: $(($allocatedSize / 1024 / 1024 / 1024)) Go" >> "$ALLOCATED_TROP_FILE"
            fi
        done
    done
done < sub.txt

echo "Script terminé. Résultats enregistrés dans :"
echo "- $PLAN_LIMITE_FILE (bases proches de la limite)"
echo "- $ALLOCATED_TROP_FILE (bases dépassant leur plan)"