#!/bin/bash

# Fichiers de sortie
ALL_BDS_FILE="toutes-les-bds.txt"
ALLOCATED_TROP_FILE="alocated-trop-grand.txt"

# Nettoyage des fichiers avant d'ajouter du contenu
> "$ALL_BDS_FILE"
> "$ALLOCATED_TROP_FILE"

echo "Début du script de vérification des bases de données..."

# En-têtes des fichiers de sortie
echo "Abonnement | Groupe de Ressources | Serveur | BD | Plan | Taille Plan (Go) | Utilisé (Go) | % Utilisation" > "$ALL_BDS_FILE"
echo "Abonnement | Groupe de Ressources | Serveur | BD | Plan | Taille Plan (Go) | Utilisé (Go) | % Utilisation | % Excès" > "$ALLOCATED_TROP_FILE"

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
        databases=$(az sql db list --server "$serverName" --resource-group "$resourceGroup" --query "[].{name:name, sku:sku.tier, maxSize:maxSizeBytes, allocatedSize:status.storageUsedInBytes}" --output json)

        # Vérifier chaque base de données
        echo "$databases" | jq -c '.[]' | while read db; do
            dbName=$(echo "$db" | jq -r '.name')
            sku=$(echo "$db" | jq -r '.sku')
            maxSize=$(echo "$db" | jq -r '.maxSize')
            allocatedSize=$(echo "$db" | jq -r '.allocatedSize')

            # Vérification si les valeurs existent
            if [[ "$maxSize" == "null" || "$allocatedSize" == "null" || "$maxSize" -eq 0 ]]; then
                continue
            fi

            # Conversion en Go
            maxSizeGB=$((maxSize / 1024 / 1024 / 1024))
            allocatedSizeGB=$((allocatedSize / 1024 / 1024 / 1024))

            # Calcul du pourcentage d'utilisation du plan
            usagePercentage=$(( (allocatedSize * 100) / maxSize ))

            # Écriture dans le fichier de toutes les BD
            echo "$subscription | $resourceGroup | $serverName | $dbName | $sku | $maxSizeGB Go | $allocatedSizeGB Go | $usagePercentage%" >> "$ALL_BDS_FILE"

            # Vérifier si la BD dépasse son plan
            if [[ $allocatedSize -gt $maxSize ]]; then
                excessPercentage=$(( (allocatedSize * 100) / maxSize - 100 ))
                echo "$subscription | $resourceGroup | $serverName | $dbName | $sku | $maxSizeGB Go | $allocatedSizeGB Go | $usagePercentage% | $excessPercentage%" >> "$ALLOCATED_TROP_FILE"
            fi
        done
    done
done < sub.txt

echo "Script terminé. Résultats enregistrés dans :"
echo "- $ALL_BDS_FILE (toutes les bases de données)"
echo "- $ALLOCATED_TROP_FILE (bases dépassant leur plan)"