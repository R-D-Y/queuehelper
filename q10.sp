for subscriptionNameActuel in $(az account list -o json | jq -r .[].name); do
  az account set --name $subscriptionNameActuel
  az sql server list -o table | grep -v ^Name | grep -v "^--" > $serverfile
  echo -e "" >> $serverfile

  while IFS='' read line
  do
     if [[ -z "$line" ]]; then
       continue
     fi

     data=$(echo "$line" | awk '{print $1" "$2}')
     rg=$(echo "$data" | cut -d " " -f 2)
     server=$(echo "$data" | cut -d " " -f 1)
     numbersOfDb=$(az sql db list --resource-group "$rg" --server "$server" --query "length(@)")
     echo "serveurActuel : $server, nbDb : $numbersOfDb"
     numbersOfDb=$((numbersOfDb-1))
     databaseList=$(az sql db list --resource-group "$rg" --server "$server")
     env=${rg:0:6}

     for i in $(seq 0 $numbersOfDb); do
       dbId=$(echo $databaseList | jq -r .[$i].databaseId)
       name=$(echo $databaseList | jq -r .[$i].name)
       status=$(echo $databaseList | jq -r .[$i].status)
       location=$(echo $databaseList | jq -r .[$i].location)
       sku=$(echo $databaseList | jq -r .[$i].sku.tier // "UNKNOWN")  # Plan de la base de données
       maxSize=$(echo $databaseList | jq -r .[$i].maxSizeBytes // 0)  # Taille max du plan en bytes
       
       guid=$(echo ${server:(-36)})
       org=$(cf curl /V3/organizations/$guid | jq -r .name)

       if [[ ! $name = *"master"* ]]; then
         nbOccurencesDb=$(cat $MYDIRFILE_OUTPUT_CSV | grep $name | wc -l)
         
         # Récupération des usages via az sql db list-usages
         dbUsages=$(az sql db list-usages --server "$server" --resource-group "$rg" --name "$name" --output json)

         usedSize=$(echo "$dbUsages" | jq -r '.[] | select(.displayName == "Database Size") | .currentValue // 0' | awk '{print int($1)}')
         allocatedSize=$(echo "$dbUsages" | jq -r '.[] | select(.name == "database_allocated_size") | .currentValue // 0' | awk '{print int($1)}')

         # Vérification si les valeurs existent
         if [[ "$maxSize" -eq 0 ]]; then
           echo "  ❌ Problème : Taille plan introuvable pour $name."
           continue
         fi

         # Conversion des tailles en Go
         maxSizeGB=$((maxSize / 1024 / 1024 / 1024))
         usedSizeGB=$((usedSize / 1024 / 1024 / 1024))
         allocatedSizeGB=$((allocatedSize / 1024 / 1024 / 1024))
         remainingSizeGB=$((maxSizeGB - usedSizeGB))

         # Calcul des pourcentages
         usagePercentage=$(( (usedSize * 100) / maxSize ))
         allocatedPercentage=$(( (allocatedSize * 100) / maxSize ))

         # Logique existante avec ajout des informations supplémentaires
         if [[ $name = *"fog"* && $nbOccurencesDb -lt 2 ]]; then
            echo "$compteur,$name,$dbId,$status,$location,$env,$server,$org,$sku,$maxSizeGB Go,$usedSizeGB Go,$allocatedSizeGB Go,$remainingSizeGB Go,$usagePercentage%,$allocatedPercentage%" >> $MYDIRFILE_OUTPUT_CSV
            echo "BD $compteur: $name de l'org: $org en $env traitée (Plan: $sku, Utilisé: $usedSizeGB Go, Alloué: $allocatedSizeGB Go)"
            compteur=$((compteur+1))
         elif [[ $nbOccurencesDb -lt 1 ]]; then
           echo "$compteur,$name,$dbId,$status,$location,$env,$server,$org,$sku,$maxSizeGB Go,$usedSizeGB Go,$allocatedSizeGB Go,$remainingSizeGB Go,$usagePercentage%,$allocatedPercentage%" >> $MYDIRFILE_OUTPUT_CSV
           echo "BD $compteur: $name de l'org: $org en $env traitée (Plan: $sku, Utilisé: $usedSizeGB Go, Alloué: $allocatedSizeGB Go)"
           compteur=$((compteur+1))
         fi
       fi
     done
   done < $serverfile
done