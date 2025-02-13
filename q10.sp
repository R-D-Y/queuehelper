# Extraire `usedSize` (espace réellement utilisé) et le convertir en entier
usedSize=$(echo "$dbUsages" | jq -r '.[] | select(.displayName == "Database Size") | .currentValue // 0')
usedSize=$(printf "%.0f\n" "$usedSize")  # Convertir en entier

# Extraire `allocatedSize` (espace alloué) et le convertir en entier
allocatedSize=$(echo "$dbUsages" | jq -r '.[] | select(.name == "database_allocated_size") | .currentValue // 0')
allocatedSize=$(printf "%.0f\n" "$allocatedSize")  # Convertir en entier

# Vérification des valeurs
if [[ "$maxSize" == "null" || -z "$maxSize" ]]; then
    echo "  ❌ Problème : maxSizeBytes introuvable pour $name."
    continue
fi

if [[ "$usedSize" -eq 0 ]]; then
    echo "  ⚠️ Attention : usedSize introuvable pour $name."
fi

if [[ "$allocatedSize" -eq 0 ]]; then
    echo "  ⚠️ Attention : allocatedSize introuvable pour $name."
fi

# Convertir maxSize en entier
maxSize=$(printf "%.0f\n" "$maxSize")

# Conversion en Go
maxSizeGB=$((maxSize / 1024 / 1024 / 1024))
usedSizeGB=$((usedSize / 1024 / 1024 / 1024))
allocatedSizeGB=$((allocatedSize / 1024 / 1024 / 1024))
remainingSizeGB=$((maxSizeGB - usedSizeGB))