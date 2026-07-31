#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "SeaCommonsImmersiveGameMode.generated.h"

UCLASS()
class SEACOMMONSIMMERSIVE_API ASeaCommonsImmersiveGameMode : public AGameModeBase
{
    GENERATED_BODY()

protected:
    virtual void BeginPlay() override;
};

